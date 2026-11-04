"""Condition/advice semantics and auditability, using local data only."""
import copy
import json
from pathlib import Path
import unittest

from task5.extract import extract, group_mappings
from task5.run import apply_reviews, validate


ROOT = Path(__file__).resolve().parents[2]


def document(text, identifier='sample', spot='杭州西湖'):
    return {'doc_id': identifier, 'scenic_spot': spot, 'source_type': 'user_generated',
            'source_name': '测试原文', 'url': 'local', 'clean_text': text}


def pairs_for(text):
    return extract([document(text)])[0]


class ConditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = [json.loads(s) for s in (ROOT / 'task1/data/final/documents.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
        cls.pairs, cls.candidates, cls.duplicates = extract(cls.docs)
        cls.mappings = group_mappings(cls.pairs)

    def test_real_data_covers_three_scenes_and_both_sources(self):
        self.assertEqual({p['scenic_spot'] for p in self.pairs}, {'北京故宫', '杭州西湖', '九寨沟'})
        self.assertEqual({p['source_type'] for p in self.pairs}, {'official', 'user_generated'})
        self.assertGreater(len(self.pairs), 30)
        self.assertTrue(any(p['doc_id'].startswith('xihu_official') for p in self.pairs))

    def test_if_rain_preserves_multiple_recommendations_and_negation(self):
        pair = pairs_for('如果下雨，山上风大，建议穿雨衣，不建议撑伞。')[0]
        self.assertEqual(pair['condition'], '下雨')
        self.assertEqual(pair['advice'], '建议穿雨衣，不建议撑伞')
        self.assertEqual(pair['condition_type'], 'weather')

    def test_suppose_and_if_without_comma(self):
        a = pairs_for('假如带老人，建议少走路。')[0]
        b = pairs_for('若下雨则穿雨衣。')[0]
        self.assertEqual(a['condition'], '带老人')
        self.assertEqual(a['condition_type'], 'visitor_type')
        self.assertEqual(b['condition'], '下雨')
        self.assertIn('穿雨衣', b['advice'])

    def test_two_conditions_in_one_sentence_do_not_cross_attach(self):
        pairs = pairs_for('如果下雨建议带伞，如果晴天建议防晒。')
        self.assertEqual([(p['condition'], p['advice']) for p in pairs], [('下雨', '建议带伞'), ('晴天', '建议防晒')])

    def test_conditional_line_can_govern_next_line(self):
        pair = next(p for p in self.pairs if p['condition'] == '是分配到右线开始')
        self.assertEqual(pair['advice'], '这边是建议放弃左线，深度玩右线')
        self.assertIn('\n', pair['source_sentence'])
        self.assertEqual(pair['condition_type'], 'route')

    def test_conditions_do_not_cross_new_headers_or_blank_paragraphs(self):
        for text in ('如果下雨：\n【另一方案】\n建议坐车。', '如果下雨：\n一、另一方案\n建议坐车。', '如果下雨：\n\n建议坐车。'):
            with self.subTest(text=text):
                self.assertEqual(pairs_for(text), [])

    def test_unconditional_and_descriptive_can_are_not_conditional(self):
        self.assertEqual(pairs_for('建议坐船。可以看到很多小鱼。这里可以拍照。'), [])

    def test_past_choice_and_counterfactual_are_not_invented_advice(self):
        self.assertEqual(pairs_for('因为阴雨天直接舍弃观赏性一般的原始森林。'), [])
        self.assertEqual(pairs_for('如果让我重新走一次，还是会选择原来的路线。'), [])
        self.assertEqual(pairs_for('如果下雨，花海很漂亮。'), [])

    def test_implicit_fitness_retains_alternative_recommendations(self):
        pair = pairs_for('体力一般建议坐环湖观光车，或者分成2天慢慢玩。')[0]
        self.assertEqual(pair['condition'], '体力一般')
        self.assertIn('或者分成2天慢慢玩', pair['advice'])
        self.assertEqual(pair['condition_type'], 'physical_condition')

    def test_category_depends_on_condition_instead_of_advice_keywords(self):
        pair = pairs_for('体力一般建议阴雨天坐车。')[0]
        self.assertNotIn('weather', pair['condition_types'])

    def test_caution_targets_its_route_and_later_summary_resets_scope(self):
        cautions = [p for p in self.pairs if p['advice'] == '慎选']
        by_condition = {p['condition']: p for p in cautions}
        self.assertIn('路线 1', by_condition['带老人小孩']['context']['text'])
        self.assertIn('路线 4', by_condition['赶时间']['context']['text'])
        summary = next(p for p in self.pairs if p['condition'] == '带娃 / 带父母')
        self.assertIsNone(summary['context'])
        self.assertIn('路线 2 或 4', summary['advice'])

    def test_official_general_tips_do_not_inherit_exhibition_heading(self):
        pair = next(p for p in self.pairs if p['condition'] == '旅游旺季参观时')
        self.assertIsNone(pair['context'])

    def test_suitable_option_keeps_stated_target_and_visitor_constraint(self):
        pair = next(p for p in self.pairs if p['condition'] == '带娃/赶时间')
        self.assertEqual(pair['advice'], '一、半天精华线')
        self.assertEqual(pair['relation'], 'suitable_option')
        self.assertEqual(pair['condition_types'], ['visitor_type', 'time'])

    def test_season_and_boat_preparation_have_exact_boundaries(self):
        season = next(p for p in self.pairs if p['condition_type'] == 'season')
        self.assertEqual(season['condition'], '每年3‑4月郁金香展')
        self.assertEqual(season['advice'], '入园需要提前预约')
        boat = next(p for p in self.pairs if p['condition'] == '打算坐船')
        self.assertEqual(boat['advice'], '出门前留意天气预报')

    def test_known_correlative_gap_is_not_returned_with_meaningless_object(self):
        self.assertEqual(pairs_for('哪天晴天选哪天。'), [])

    def test_repeated_segment_warning_is_one_mapping_with_two_positions(self):
        group = next(g for g in self.mappings if g['condition'] == '天鹅海→箭竹海')
        self.assertEqual(group['advice'], '不建议徒步')
        self.assertEqual(len(group['occurrences']), 2)
        self.assertEqual(len(set(group['occurrences'])), 2)

    def test_rule_overlap_is_suppressed_at_same_position(self):
        accepted, _, duplicates = extract([document('如果体力一般建议坐车。')])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0]['rule'], 'explicit_condition')
        self.assertEqual(len(duplicates), 1)

    def test_mapping_grouping_never_merges_opposite_recommendations(self):
        groups = group_mappings(pairs_for('如果下雨建议坐车。\n如果下雨不建议坐车。'))
        self.assertEqual(len(groups), 2)

    def test_long_near_duplicate_prefixes_group_without_losing_occurrences(self):
        groups = group_mappings(pairs_for('如果下雨建议坐环湖观光车到下一站继续游玩。\n如果下雨建议坐环湖观光车到下一站继续游玩拍照。'))
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['dedup_method'], 'normalized_prefix')
        self.assertEqual(len(groups[0]['occurrences']), 2)
        below_threshold = group_mappings(pairs_for('如果下雨建议坐环湖观光车到下一站。\n如果下雨建议坐环湖观光车到下一站游览。'))
        self.assertEqual(len(below_threshold), 2)

    def test_prefix_merging_preserves_added_negation_and_numbers(self):
        text = '如果下雨建议坐环湖观光车到下一站继续游玩。\n如果下雨建议坐环湖观光车到下一站继续游玩不要。'
        self.assertEqual(len(group_mappings(pairs_for(text))), 2)
        text = '如果下雨建议坐环湖观光车到下一站继续游玩。\n如果下雨建议坐环湖观光车到下一站继续游玩20分钟。'
        self.assertEqual(len(group_mappings(pairs_for(text))), 2)

    def test_same_warning_on_different_routes_stays_separate(self):
        text = '🗺️路线 1（红线）：东华门→午门\n带老人小孩慎选。\n🗺️路线 2（绿线）：公园→午门\n带老人小孩慎选。'
        self.assertEqual(len(group_mappings(pairs_for(text))), 2)

    def test_full_line_retains_the_ticket_target_before_exclamation(self):
        pair = next(p for p in self.pairs if p['condition'] == '没约上')
        self.assertIn('珍宝馆、钟表馆', pair['source_sentence'])
        self.assertEqual(pair['advice'], '可到展馆门口买')

    def test_unresolved_full_document_reference_is_marked(self):
        pair = next(p for p in self.pairs if p['advice'] == '可以直接抄')
        self.assertTrue(pair['requires_context'])

    def test_unicode_and_all_real_offsets_match(self):
        doc = document('🌿体力一般建议坐车。')
        pairs = extract([doc])[0]
        self.assertEqual(pairs[0]['condition_span']['start'], 1)
        self.assertEqual(validate(pairs, [doc]), 3)
        self.assertGreater(validate(self.pairs, self.docs), 130)

    def test_wrong_span_is_detected(self):
        pair = copy.deepcopy(self.pairs[0])
        pair['advice_span']['start'] += 1
        with self.assertRaises(ValueError):
            validate([pair], self.docs)

    def test_reviews_confirm_reject_and_add_with_audit_log(self):
        doc = document('体力一般建议坐车。时间充足可以慢慢走。')
        pairs = extract([doc])[0]
        confirmed, log = apply_reviews(pairs, [doc], [{'action': 'confirm', 'advice_id': pairs[0]['advice_id'], 'note': '核对原文'}])
        self.assertEqual(confirmed[0]['review_status'], 'reviewed')
        self.assertEqual(len(log), 1)
        rejected, _ = apply_reviews(pairs, [doc], [{'action': 'reject', 'advice_id': pairs[0]['advice_id']}])
        self.assertEqual(len(rejected), len(pairs) - 1)
        added, _ = apply_reviews([], [doc], [{'action': 'add', 'doc_id': 'sample', 'condition_start': 0, 'condition_end': 4, 'advice_start': 4, 'advice_end': 8}])
        self.assertEqual(added[0]['advice'], '建议坐车')
        validate(added, [doc])

    def test_review_replace_and_invalid_targets_fail_explicitly(self):
        doc = document('体力一般建议坐车。')
        pairs = extract([doc])[0]
        updated, _ = apply_reviews(pairs, [doc], [{'action': 'replace', 'advice_id': pairs[0]['advice_id'], 'doc_id': 'sample', 'condition_start': 0, 'condition_end': 4, 'advice_start': 4, 'advice_end': 8, 'condition_type': 'physical_condition'}])
        self.assertEqual(updated[0]['rule'], 'review')
        with self.assertRaises(ValueError):
            apply_reviews(pairs, [doc], [{'action': 'reject', 'advice_id': 'unknown'}])
        with self.assertRaises(ValueError):
            apply_reviews([], [doc], [{'action': 'add', 'doc_id': 'sample', 'condition_start': -1, 'condition_end': 4, 'advice_start': 4, 'advice_end': 8}])

    def test_review_replace_preserves_real_context_and_relation(self):
        for condition in ('带老人小孩', '带娃/赶时间'):
            pair = next(p for p in self.pairs if p['condition'] == condition)
            review = {'action': 'replace', 'advice_id': pair['advice_id'], 'doc_id': pair['doc_id'],
                      'condition_start': pair['condition_span']['start'], 'condition_end': pair['condition_span']['end'],
                      'advice_start': pair['advice_span']['start'], 'advice_end': pair['advice_span']['end'],
                      'condition_type': pair['condition_type']}
            with self.subTest(condition=condition):
                result, _ = apply_reviews([pair], self.docs, [review])
                self.assertEqual(result[0]['context'], pair['context'])
                self.assertEqual(result[0]['relation'], pair['relation'])
                self.assertFalse(result[0]['requires_context'])
                validate(result, self.docs)

    def test_review_moved_to_another_route_rebinds_context(self):
        text = '🗺️路线 1（红线）：东华门→午门\n带老人小孩慎选。\n🗺️路线 2（绿线）：公园→午门\n带老人小孩慎选。'
        doc = document(text)
        pairs = extract([doc])[0]
        first, second = pairs
        review = {'action': 'replace', 'advice_id': first['advice_id'], 'doc_id': doc['doc_id'],
                  'condition_start': second['condition_span']['start'], 'condition_end': second['condition_span']['end'],
                  'advice_start': second['advice_span']['start'], 'advice_end': second['advice_span']['end']}
        result, _ = apply_reviews([first], [doc], [review])
        self.assertIn('路线 2', result[0]['context']['text'])
        validate(result, [doc])
        added, _ = apply_reviews([], [doc], [{**review, 'action': 'add'}])
        self.assertIn('路线 2', added[0]['context']['text'])

    def test_review_add_supports_explicit_context_and_validates_it(self):
        doc = document('东门接驳方案\n带老人小孩慎选。')
        text = doc['clean_text']
        ca, aa = text.index('带老人小孩'), text.index('慎选')
        review = {'action': 'add', 'doc_id': doc['doc_id'], 'condition_start': ca, 'condition_end': ca + len('带老人小孩'),
                  'advice_start': aa, 'advice_end': aa + len('慎选'), 'context_start': 0, 'context_end': len('东门接驳方案')}
        result, _ = apply_reviews([], [doc], [review])
        self.assertEqual(result[0]['context']['text'], '东门接驳方案')
        self.assertFalse(result[0]['requires_context'])
        validate(result, [doc])
        with self.assertRaises(ValueError):
            apply_reviews([], [doc], [{**review, 'context_end': len(text) + 1}])

    def test_review_without_a_caution_target_is_flagged(self):
        doc = document('带老人小孩慎选。')
        result, _ = apply_reviews([], [doc], [{'action': 'add', 'doc_id': doc['doc_id'], 'condition_start': 0,
                                            'condition_end': 5, 'advice_start': 5, 'advice_end': 7}])
        self.assertIsNone(result[0]['context'])
        self.assertTrue(result[0]['requires_context'])


if __name__ == '__main__':
    unittest.main()
