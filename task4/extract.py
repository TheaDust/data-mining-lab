"""Chinese pronoun detection, candidate generation and coreference resolution.

The module is deliberately rule based.  It uses only the Python standard library
so that the experiment can be re-run offline.  All character offsets are Python
Unicode code points into the original ``clean_text`` (0-based, half-open).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Longest surfaces must be tried first so that "这里" is not found as "这".
PRONOUN_SURFACES = [
    "它们", "他们", "她们", "我们", "你们", "咱们", "自己", "大家",
    "这里", "这儿", "那里", "那儿", "这边", "那边", "此处", "此地",
    "这个", "那个", "这些", "那些", "这样", "那样", "这种", "那种",
    "它", "他", "她", "我", "你", "此", "该", "其", "这", "那",
]
PRONOUN_RE = re.compile("|".join(sorted(map(re.escape, PRONOUN_SURFACES), key=len, reverse=True)))

PERSON_NOUNS = ["孩子", "娃", "小朋友", "老人", "家长", "作者", "同伴", "家人"]

PALACE_HEADS = {"皇城", "围墙", "紫禁城", "故宫"}
POI_HEADS = {
    "门", "宫", "殿", "园", "海", "塔", "桥", "寺", "山", "湖", "景点",
    "景区", "机位", "地方", "院落", "宫殿", "城", "皇城", "围墙", "建筑",
    "公园", "码头", "车站", "中心", "站", "点", "楼", "阁", "亭", "馆",
    "紫禁城", "故宫",
}
ROUTE_HEADS = {"路线", "线路", "线", "段", "行程", "方案", "路线图"}
TRANSPORT_HEADS = {"交通方式", "车", "船", "观光车", "自行车", "大巴", "地铁", "索道"}
NON_ENTITY_HEADS = {
    "照片", "经验", "故事", "问题", "时候", "时间", "次", "篇", "种", "样",
    "感觉", "特点", "方式", "事情", "内容", "文章", "攻略", "视频",
    "历史疑案", "疑案", "案件", "句话", "话", "趣闻", "布局", "形式",
    "制度", "设计", "两个", "两个地方", "期间", "位",
}

# Head phrases after the pronoun.  The first matching pattern wins.
HEAD_PATTERNS = [
    (re.compile(r"^(?:一)?条路线"), "路线"),
    (re.compile(r"^(?:一)?条线路"), "线路"),
    (re.compile(r"^(?:一)?条线(?!路)"), "线"),
    (re.compile(r"^(?:一)?段"), "段"),
    (re.compile(r"^(?:一)?道门"), "门"),
    (re.compile(r"^(?:一)?座(皇城|围墙|宫殿|建筑|城)"), None),
    (re.compile(r"^(?:一)?个(机位|景点|景区|路线|院落|地方|宫殿|公园|码头|车站|中心)"), None),
    (re.compile(r"^(?:一)?些(照片|经验|故事|问题|打卡点|景点)"), None),
    (re.compile(r"^(?:一)?篇"), "篇"),
    (re.compile(r"^(?:一)?种"), "种"),
    (re.compile(r"^(?:一)?次"), "次"),
    (re.compile(r"^(?:一)?时"), "时间"),
    (re.compile(r"^(?:一)?句话"), "句话"),
    (re.compile(r"^两个"), "两个"),
    (re.compile(r"^位"), "位"),
    (re.compile(r"^(?:一)?(紫禁城|故宫|皇城)"), None),
]

# Aliases used only for head-noun matching.  They do not merge entities.
HEAD_ALIASES = {
    "皇城": ["紫禁城", "故宫", "故宫博物院"],
    "围墙": ["紫禁城", "故宫"],
    "紫禁城": ["故宫", "皇城"],
    "故宫": ["紫禁城", "故宫博物院", "皇城"],
    "机位": ["柳浪闻莺", "太子湾公园"],
}

# Candidate source weights.
SOURCE_BONUS = {
    "heading": 2.0,
    "route_segment": 1.2,
    "compound_route": 1.5,
    "entity": 0.5,
    "person": 0.8,
}

RESOLVE_THRESHOLD = 2.0
AMBIGUOUS_MARGIN = 0.35


# ---------------------------------------------------------------------------
# Small data structures
# ---------------------------------------------------------------------------

@dataclass
class Sentence:
    start: int
    end: int
    text: str


@dataclass
class Candidate:
    text: str
    start: int
    end: int
    type: str
    source: str
    section_start: int | None = None
    section_end: int | None = None
    meta: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "type": self.type,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Remove whitespace, punctuation and emoji for name comparison."""
    return re.sub(r"[\s\W_]+", "", text or "")


def split_sentences(text: str) -> list[Sentence]:
    """Split on sentence punctuation and newlines, keeping spans in the source."""
    sentences: list[Sentence] = []
    start = 0
    for match in re.finditer(r"[。！？!?；;\n]", text):
        end = match.end()
        piece = text[start:end]
        if piece.strip():
            sentences.append(Sentence(start, end, piece))
        start = end
    if start < len(text):
        piece = text[start:]
        if piece.strip():
            sentences.append(Sentence(start, len(text), piece))
    return sentences


def sentence_index(sentences: list[Sentence], position: int) -> int:
    for index, sentence in enumerate(sentences):
        if sentence.start <= position < sentence.end:
            return index
    return len(sentences) - 1


def iter_lines(text: str) -> Iterable[tuple[int, int, str]]:
    start = 0
    for match in re.finditer(r"\n", text):
        yield start, match.start(), text[start:match.start()]
        start = match.end()
    if start < len(text):
        yield start, len(text), text[start:]


def inside_hashtag_or_url(text: str, start: int, end: int) -> bool:
    line_start = text.rfind("\n", 0, start) + 1
    prefix = text[line_start:start]
    if "#" in prefix:
        tag = prefix[prefix.rfind("#"):]
        if " " not in tag and "\t" not in tag:
            return True
    return bool(re.search(r"https?://\S*$", prefix))


def strip_leading_symbols(line: str) -> str:
    # Remove emoji, bullets, circled numbers and spaces before the first word.
    stripped = re.sub(r"^[^\u4e00-\u9fffA-Za-z0-9]+", "", line.strip())
    # Remove leading Arabic numbers and their keycap/variation selectors.
    stripped = re.sub(r"^[0-9]+\ufe0f?\u20e3?\s*", "", stripped)
    return stripped.strip()


# ---------------------------------------------------------------------------
# Pronoun detection
# ---------------------------------------------------------------------------

def classify_mention(text: str, surface: str, start: int, end: int) -> dict:
    """Return the pronoun type, optional head noun and initial status."""
    after = text[end:]
    head = None

    if surface in {"这", "那"} and after.startswith(("并不", "不就", "这不", "那不", "才是", "才真正", "才叫")):
        # "这并不影响……" / "这不就是……" / "这才是……" are discourse
        # comments, not references to a named place.
        return {
            "kind": "discourse",
            "pronoun_type": "discourse",
            "head": None,
            "head_type": None,
            "status": "non_entity",
        }

    if surface in {"这个", "那个"}:
        if after.startswith("感觉"):
            # "对这个感觉一般" uses 感觉 as a verb: "这个" is the object.
            head = None
        else:
            # "这个机位" / "这个路线" etc. are determiners; "这个我喜欢"
            # is a demonstrative pronoun.
            for candidate_head in sorted(
                POI_HEADS | ROUTE_HEADS | TRANSPORT_HEADS | NON_ENTITY_HEADS,
                key=len,
                reverse=True,
            ):
                if after.startswith(candidate_head):
                    head = candidate_head
                    break
        kind = "determiner" if head else "demonstrative"
    elif surface in {"这些", "那些", "这种", "那种"}:
        for candidate_head in sorted(
            POI_HEADS | ROUTE_HEADS | TRANSPORT_HEADS | NON_ENTITY_HEADS,
            key=len,
            reverse=True,
        ):
            if after.startswith(candidate_head):
                head = candidate_head
                break
        if head is None and after.startswith("打卡点"):
            head = "打卡点"
        kind = "determiner" if head else "discourse"
    elif surface in {"这", "那", "此", "该", "其"}:
        for pattern, fixed_head in HEAD_PATTERNS:
            match = pattern.match(after)
            if match:
                head = fixed_head or match.group(1)
                break
        if head is None:
            # "这条的..." / "这才是..." / "这是..." are pronouns, not
            # determiners.  Do not use the measure word as a head noun.
            kind = "demonstrative"
        else:
            kind = "determiner"
        if surface == "该" and head is None:
            kind = "discourse"
        if surface == "其" and head is None:
            kind = "discourse"
    else:
        kind = "pronoun"

    if surface in {"这里", "这儿", "那里", "那儿", "这边", "那边", "此处", "此地"}:
        pronoun_type = "place"
    elif surface in {"它", "它们"}:
        pronoun_type = "object"
    elif surface in {"他们", "她们", "他", "她"}:
        pronoun_type = "person_third"
    elif surface in {"我们", "咱们", "我"}:
        pronoun_type = "person_first"
    elif surface in {"你们", "你"}:
        pronoun_type = "person_second"
    elif surface in {"自己"}:
        pronoun_type = "person_reflexive"
    elif surface in {"大家"}:
        pronoun_type = "person_generic"
    elif surface in {"这样", "那样"}:
        pronoun_type = "discourse"
    elif kind == "determiner":
        pronoun_type = "determiner"
    else:
        pronoun_type = "demonstrative"
    if kind == "discourse":
        pronoun_type = "discourse"

    head_type = None
    if head:
        if head in ROUTE_HEADS:
            head_type = "route"
        elif head in TRANSPORT_HEADS:
            head_type = "transport"
        elif head in POI_HEADS or head == "打卡点":
            head_type = "poi"
        elif head in NON_ENTITY_HEADS:
            head_type = "non_entity"
        else:
            head_type = "unknown"
    if surface in {"这些", "那些"} and head in {"院落", "宫殿", "景点", "地方"}:
        # A plural collective such as "这些小院落" cannot be reduced to one
        # singular POI without a list-level antecedent.
        head_type = "non_entity"

    if pronoun_type in {"person_first", "person_second", "person_reflexive", "person_generic"}:
        status = "out_of_scope"
    elif pronoun_type == "person_third":
        status = "candidate"
    elif pronoun_type == "discourse":
        status = "non_entity"
    elif head_type == "non_entity":
        status = "non_entity"
    else:
        status = "candidate"

    return {
        "kind": kind,
        "pronoun_type": pronoun_type,
        "head": head,
        "head_type": head_type,
        "status": status,
    }


def replacement_suffix(surface: str, after: str, head: str | None) -> str:
    """Characters after the pronoun that belong to the same anaphoric NP.

    Replacing "这条路线" as a whole is grammatical; replacing only "这" leaves
    "……条路线".  For "这个路线" the measure word is already inside the surface,
    so only the head noun is consumed.
    """
    if not head:
        return ""
    if surface in {"这个", "那个", "这些", "那些", "这种", "那种"}:
        index = after.find(head)
        return after[:index + len(head)] if index != -1 else head
    if surface in {"这", "那", "此", "该", "其"}:
        index = after.find(head)
        return after[:index + len(head)] if index != -1 else head
    return ""


def detect_pronouns(text: str) -> list[dict]:
    """Detect pronoun and demonstrative mentions with source offsets."""
    sentences = split_sentences(text)
    mentions: list[dict] = []

    for match in PRONOUN_RE.finditer(text):
        surface = match.group()
        start, end = match.start(), match.end()
        prev_char = text[start - 1] if start else ""
        after = text[end:]

        if inside_hashtag_or_url(text, start, end):
            continue

        # Fixed compounds containing a pronoun character.
        if surface in {"他", "她", "它"} and prev_char == "其":
            continue
        if surface == "其" and (prev_char in "尤极与" or after.startswith(("实", "中", "他", "它", "余"))):
            continue
        if surface == "此" and (prev_char in "从因如此就彼" or after.startswith(("外", "前", "后", "时", "刻", "举", "类", "行", "文", "事", "次"))):
            continue
        if surface == "该" and after.startswith(("坐", "去", "是", "有", "如", "怎", "不", "要", "会", "可", "应", "当", "把", "被", "让", "给", "对", "来", "走", "用", "加", "减", "换", "买", "吃", "住", "看", "玩")):
            continue
        if surface == "这" and after.startswith(("次", "篇", "样", "么", "时", "回", "下", "儿", "期间")):
            # Temporal / discourse uses are kept as non-entity mentions only
            # when they are not just part of a fixed phrase.
            if after.startswith(("次", "时", "回", "下", "儿", "期间", "么")):
                continue
        if surface == "那" and after.startswith(("年", "天", "时", "回", "下", "儿", "么")):
            continue
        if surface == "这" and prev_char == "就" and after.startswith(("？", "?", "！", "!")):
            continue

        info = classify_mention(text, surface, start, end)
        suffix = replacement_suffix(surface, text[end:], info["head"])
        sent_index = sentence_index(sentences, start)
        sentence = sentences[sent_index]
        mentions.append({
            "doc_id": None,
            "surface": surface,
            "start": start,
            "end": end,
            "replace_end": end + len(suffix),
            "replace_text": text[start:end + len(suffix)],
            "sentence": sentence.text,
            "sentence_start": sentence.start,
            "sentence_end": sentence.end,
            "sentence_index": sent_index,
            **info,
        })

    return mentions


# ---------------------------------------------------------------------------
# Candidate generation
# ---------------------------------------------------------------------------

def heading_name(line: str, poi_texts: set[str]) -> tuple[str, int] | None:
    """Return (name, offset_in_line) when a line looks like a section heading."""
    stripped = line.strip()
    if not stripped or "→" in stripped:
        return None

    marked = (
        "｜" in stripped
        or "|" in stripped
        or stripped.startswith("📍")
        or re.match(r"^[^\u4e00-\u9fffA-Za-z]+", stripped) is not None
        or (stripped.endswith("：") and len(stripped) <= 30)
    )
    if not marked:
        return None

    candidate = strip_leading_symbols(stripped)
    for name in sorted(poi_texts, key=len, reverse=True):
        if candidate.startswith(name):
            return name, line.find(name)
    return None


def extract_arrow_nodes(line: str, line_start: int, poi_names: set[str]) -> list[tuple[int, int]]:
    """Extract POI nodes from an arrow chain, ignoring leading emoji/advice."""
    parts: list[tuple[int, str]] = []
    position = 0
    for match in re.finditer(r"→|->", line):
        parts.append((position, line[position:match.start()]))
        position = match.end()
    parts.append((position, line[position:]))

    nodes: list[tuple[int, int]] = []
    for raw_start, raw in parts:
        # Pick the earliest POI in the node, preferring the longer name on a
        # tie.  This keeps "花港观鱼（对面就是太子湾公园）" as 花港观鱼 and
        # still finds "然后坐船看三潭印月".
        best: tuple[int, str] | None = None
        best_key: tuple[int, int] | None = None
        for name in poi_names:
            offset = raw.find(name)
            if offset == -1:
                continue
            key = (offset, -len(name))
            if best_key is None or key < best_key:
                best_key = key
                best = (offset, name)
        if best is not None:
            offset, name = best
            start = line_start + raw_start + offset
            nodes.append((start, start + len(name)))
    return sorted(nodes)


def build_candidates(
    text: str,
    entities: list[dict],
    extra_poi_names: set[str] | None = None,
) -> list[Candidate]:
    """Build entity, heading, route-segment and person antecedent candidates."""
    candidates: list[Candidate] = []
    extra_poi_names = extra_poi_names or set()

    def add(candidate: Candidate) -> None:
        if candidate.start > candidate.end:
            return
        if candidate.text != text[candidate.start:candidate.end]:
            return
        candidates.append(candidate)

    # 1. POI and transport mentions from the upstream entity task.
    for entity in entities:
        etype = entity.get("type")
        if etype not in {"POI", "TRANSPORT"}:
            continue
        start, end = entity["start"], entity["end"]
        add(Candidate(text[start:end], start, end, etype, "entity"))

    # 2. Section headings such as "午门｜..." or "📍原始森林（...）".
    poi_texts = {e["text"] for e in entities if e.get("type") == "POI"} | extra_poi_names
    lines = list(iter_lines(text))
    headings: list[tuple[int, int, str]] = []
    for line_start, line_end, line in lines:
        found = heading_name(line, poi_texts)
        if not found:
            continue
        name, offset = found
        headings.append((line_start, line_end, name))
    for index, (line_start, line_end, name) in enumerate(headings):
        section_end = headings[index + 1][0] if index + 1 < len(headings) else len(text)
        start = line_start + text[line_start:line_end].find(name)
        add(Candidate(name, start, start + len(name), "POI", "heading", line_start, section_end))

    # 3. Arrow chains and hyphen chains.  Parse the visible nodes first so a
    #    missed entity such as "珍珠滩" can still start the segment; fall back
    #    to POI entities on the line for chains with a prose prefix.
    for line_start, line_end, line in lines:
        if "→" not in line and "->" not in line and not re.search(r"[-–—]", line):
            continue
        nodes = extract_arrow_nodes(line, line_start, poi_texts)
        if len(nodes) >= 2:
            start, end = nodes[0][0], nodes[-1][1]
            add(Candidate(text[start:end], start, end, "ROUTE_SEGMENT", "route_segment"))
            continue
        line_entities = [
            e for e in entities
            if e.get("type") == "POI"
            and line_start <= e.get("start", -1) < line_end
        ]
        unique: dict[tuple[int, int], dict] = {}
        for entity in line_entities:
            unique[(entity["start"], entity["end"])] = entity
        line_entities = sorted(unique.values(), key=lambda e: e["start"])
        if len(line_entities) < 2:
            continue
        start = line_entities[0]["start"]
        end = line_entities[-1]["end"]
        add(Candidate(text[start:end], start, end, "ROUTE_SEGMENT", "route_segment"))

    # 4. Compound route names such as "乌龟潭路线".
    for entity in entities:
        if entity.get("type") != "POI":
            continue
        tail = text[entity["end"]:entity["end"] + 4]
        match = re.match(r"\s*路线", tail)
        if match:
            add(Candidate(
                text[entity["start"]:entity["end"] + match.end()],
                entity["start"],
                entity["end"] + match.end(),
                "ROUTE",
                "compound_route",
            ))

    # 5. Person nouns.  They are used only for third-person pronouns.
    for noun in PERSON_NOUNS:
        for match in re.finditer(re.escape(noun), text):
            add(Candidate(noun, match.start(), match.end(), "PERSON", "person"))

    # Deduplicate identical spans/types and keep a deterministic order.
    deduped: dict[tuple[int, int, str], Candidate] = {}
    for candidate in candidates:
        deduped[(candidate.start, candidate.end, candidate.type)] = candidate
    return sorted(deduped.values(), key=lambda c: (c.start, -(c.end - c.start), c.type))


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

def type_compatible(mention: dict, candidate: Candidate) -> bool:
    pronoun_type = mention["pronoun_type"]
    head_type = mention.get("head_type")

    if pronoun_type == "person_third":
        return candidate.type == "PERSON"
    if mention.get("head") in PALACE_HEADS:
        return candidate.type == "POI" and any(
            normalize(alias) in normalize(candidate.text)
            for alias in ["紫禁城", "故宫", "皇城"]
        )
    if head_type == "route":
        return candidate.type in {"ROUTE", "ROUTE_SEGMENT", "POI"}
    if head_type == "poi":
        return candidate.type == "POI"
    if head_type == "transport":
        return candidate.type == "TRANSPORT"
    if head_type == "non_entity":
        return False
    if head_type == "person":
        return candidate.type == "PERSON"
    if pronoun_type == "place":
        return candidate.type in {"POI", "ROUTE", "ROUTE_SEGMENT"}
    if pronoun_type == "object":
        return candidate.type in {"POI", "TRANSPORT", "ROUTE_SEGMENT"}
    if pronoun_type in {"demonstrative", "determiner"}:
        return candidate.type in {"POI", "ROUTE", "ROUTE_SEGMENT", "TRANSPORT"}
    return False


def head_matches(head: str, candidate: Candidate) -> bool:
    if not head:
        return False
    normalized_head = normalize(head)
    normalized_candidate = normalize(candidate.text)
    if normalized_head and normalized_head in normalized_candidate:
        return True
    for alias in HEAD_ALIASES.get(head, []):
        if normalize(alias) in normalized_candidate:
            return True
    return False


def score_candidate(
    mention: dict,
    candidate: Candidate,
    text: str,
    active_heading_start: int | None,
) -> tuple[float, dict]:
    features: dict[str, float | bool | str] = {}
    score = 2.0  # type compatibility baseline (candidates are pre-filtered)
    features["type"] = candidate.type

    score += SOURCE_BONUS.get(candidate.source, 0.0)
    features["source"] = candidate.source

    sentence_distance = mention["sentence_index"] - sentence_index(
        split_sentences(text), candidate.start
    )

    if candidate.source == "heading" and candidate.section_start == active_heading_start:
        # A very distant section heading is usually a chapter label, not the
        # antecedent of a local "这里".  Keep the bonus for nearby headings.
        # A route-head mention ("这一段/这条路线") also prefers the actual
        # route segment over the enclosing "右线" chapter label.
        if mention["pronoun_type"] == "place" and sentence_distance >= 4:
            score += 0.0
            features["active_heading"] = False
        elif mention.get("head_type") == "route" and candidate.type == "POI":
            score += 0.0
            features["active_heading"] = False
        elif mention.get("head") in PALACE_HEADS:
            score += 0.0
            features["active_heading"] = False
        else:
            score += 2.0
            features["active_heading"] = True
    else:
        features["active_heading"] = False

    if sentence_distance == 0:
        score += 0.8
        features["same_sentence"] = True
    else:
        features["same_sentence"] = False
        score -= 0.5 * min(max(sentence_distance, 0), 5)
    features["sentence_distance"] = sentence_distance

    distance = mention["start"] - candidate.end
    score -= min(max(distance, 0), 800) / 120.0
    features["distance"] = distance
    if 0 <= distance <= 20:
        score += 0.25
        features["near_candidate"] = True

    # "这里" normally points to a nearby place.  A route segment two or more
    # sentences back is more likely discourse context, so require stronger
    # evidence before resolving it.
    if (
        mention["pronoun_type"] == "place"
        and candidate.type == "ROUTE_SEGMENT"
        and sentence_distance >= 2
    ):
        score -= 2.0
        features["distant_route_penalty"] = True
    if (
        mention["pronoun_type"] == "place"
        and candidate.type == "ROUTE_SEGMENT"
        and len(candidate.text) > 40
    ):
        score -= 1.5
        features["long_route_penalty"] = True

    if mention.get("head"):
        if head_matches(mention["head"], candidate):
            score += 2.5
            features["head_match"] = True
        else:
            features["head_match"] = False
        if mention.get("head_type") == "route" and candidate.type in {"ROUTE", "ROUTE_SEGMENT"}:
            score += 1.0
            features["route_head"] = True
        if mention.get("head_type") == "transport" and candidate.type == "TRANSPORT":
            score += 1.0
            features["transport_head"] = True
        if mention.get("head_type") == "poi" and candidate.type == "POI":
            score += 0.5
            features["poi_head"] = True

    if mention["pronoun_type"] == "place" and candidate.type == "ROUTE_SEGMENT":
        score += 0.5
        features["place_route"] = True

    frequency = text.count(candidate.text)
    score += 0.03 * min(frequency, 5)
    features["frequency"] = frequency
    score += min(len(candidate.text), 80) / 200.0
    features["length"] = len(candidate.text)

    return score, features


def resolve_document(
    doc: dict,
    entities: list[dict],
    extra_poi_names: set[str] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Detect mentions, generate candidates and resolve one document."""
    text = doc["clean_text"]
    mentions = detect_pronouns(text)
    candidates = build_candidates(text, entities, extra_poi_names)

    heading_starts = [
        c.section_start for c in candidates
        if c.source == "heading" and c.section_start is not None
    ]

    results: list[dict] = []
    for index, mention in enumerate(mentions, start=1):
        mention["doc_id"] = doc["doc_id"]
        mention["mention_id"] = f"pm_{index:04d}"
        mention["scenic_spot"] = doc["scenic_spot"]
        mention["source_type"] = doc["source_type"]
        mention["source_name"] = doc["source_name"]
        mention["url"] = doc["url"]

        if mention["status"] in {"out_of_scope", "non_entity"}:
            mention.update({
                "resolution_status": mention["status"],
                "antecedent": None,
                "antecedent_start": None,
                "antecedent_end": None,
                "antecedent_type": None,
                "confidence": 0.0,
                "candidates": [],
            })
            results.append(mention)
            continue

        active_heading_start = max(
            [h for h in heading_starts if h <= mention["start"]],
            default=None,
        )
        scored = []
        for candidate in candidates:
            if candidate.start >= mention["start"]:
                continue
            if not type_compatible(mention, candidate):
                continue
            score, features = score_candidate(mention, candidate, text, active_heading_start)
            scored.append((score, candidate, features))
        scored.sort(key=lambda item: item[0], reverse=True)

        top = scored[0] if scored else None
        second = scored[1] if len(scored) > 1 else None
        if top is None or top[0] < RESOLVE_THRESHOLD:
            status = "no_antecedent"
        elif second is not None and top[0] - second[0] < AMBIGUOUS_MARGIN:
            status = "ambiguous"
        else:
            status = "resolved"
        # "这座皇城/这座围墙/这紫禁城" has a lexical head with only a few
        # possible referents; accept the nearest palace candidate even when
        # distance makes the generic score fall below the threshold.
        if status != "resolved" and mention.get("head") in PALACE_HEADS and top is not None:
            status = "resolved"

        mention["resolution_status"] = status
        mention["candidates"] = [
            {
                **candidate.as_dict(),
                "score": round(score, 3),
                "features": features,
            }
            for score, candidate, features in scored[:5]
        ]
        if status == "resolved" or (status == "ambiguous" and top is not None):
            score, candidate, _ = top
            mention.update({
                "antecedent": candidate.text,
                "antecedent_start": candidate.start,
                "antecedent_end": candidate.end,
                "antecedent_type": candidate.type,
                "confidence": round(1.0 / (1.0 + math.exp(-(score - 2.5))), 3),
            })
        else:
            mention.update({
                "antecedent": None,
                "antecedent_start": None,
                "antecedent_end": None,
                "antecedent_type": None,
                "confidence": 0.0,
            })
        results.append(mention)

    return results, candidates


# ---------------------------------------------------------------------------
# Scoring helpers used by evaluation
# ---------------------------------------------------------------------------

def antecedent_match(predicted: str | None, gold: str | None) -> bool:
    """Name-level comparison tolerant to duplicated arrows/emoji/spacing."""
    if predicted is None or gold is None:
        return False
    p, g = normalize(predicted), normalize(gold)
    if not p or not g:
        return False
    if p == g:
        return True
    if p in g or g in p:
        return min(len(p), len(g)) / max(len(p), len(g)) >= 0.6
    return False
