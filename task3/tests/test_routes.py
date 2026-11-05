"""Targeted semantic and provenance checks against the frozen local corpus."""
import copy
import json
from pathlib import Path
import unittest

from task3.extract import (
    add_hierarchy, comparisons, lcs_length, metrics, official_routes,
    parse_gugong, parse_xihu, sequence, visitor_routes,
)
from task3.run import check_evidence, validate


ROOT = Path(__file__).resolve().parents[2]


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = [json.loads(s) for s in (ROOT / 'task1/data/final/documents.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
        cls.entities = json.loads((ROOT / 'task2/results/v2/entities.json').read_text(encoding='utf-8'))
        cls.officials = official_routes(cls.docs, cls.entities)
        selections = json.loads((ROOT / 'task3/samples.json').read_text(encoding='utf-8'))
        cls.visitors = visitor_routes(cls.docs, cls.entities, cls.officials, selections)

    def official(self, spot, index=0):
        return [r for r in self.officials if r['scenic_spot'] == spot][index]

    def test_all_seventeen_official_alternatives_remain_separate(self):
        self.assertEqual([len([r for r in self.officials if r['scenic_spot'] == s]) for s in ('北京故宫', '杭州西湖', '九寨沟')], [4, 10, 3])

    def test_gugong_main_axis_has_source_order(self):
        self.assertEqual(sequence(self.official('北京故宫')), ['午门', '太和殿', '中和殿', '保和殿', '乾清宫', '交泰殿', '坤宁宫', '御花园', '神武门'])

    def test_composite_route_does_not_invent_main_axis_expansion(self):
        route = self.official('北京故宫', 1)
        self.assertEqual(route['components'][0]['text'], '中轴线+东线')
        self.assertEqual(route['steps'][0]['poi'], '承乾宫')
        self.assertEqual(route['steps'][4]['poi'], '钟表馆')
        self.assertNotIn('太和殿', sequence(route))

    def test_unknown_time_is_not_invented_from_duration(self):
        route = self.official('杭州西湖')
        self.assertEqual(route['duration_text'], '约3小时')
        self.assertTrue(all(s['time_period'] is None and s['time_text'] is None for s in route['steps']))
        self.assertIsNone(route['hierarchy'][0]['periods'][0]['time_period'])

    def test_xihu_titles_and_durations_do_not_leak_between_routes(self):
        self.assertIsNone(self.official('杭州西湖', 1)['duration_text'])
        self.assertEqual(self.official('杭州西湖', 4)['duration_text'], '约3-4小时')
        self.assertEqual(self.official('杭州西湖', 9)['route_name'], '龙井八景')

    def test_parallel_nodes_and_parentheticals_do_not_create_false_order(self):
        route = self.official('杭州西湖', 2)
        self.assertEqual([p['name'] for p in route['steps'][2]['pois']], ['药王庙', '阮公祠'])
        self.assertEqual(route['steps'][2]['poi_order'], 'unspecified')
        self.assertNotIn('青衣洞', [p['name'] for s in route['steps'] for p in s['pois']])
        self.assertNotIn('→', route['steps'][2]['poi'])
        with self.assertRaises(ValueError):
            sequence(route)

    def test_distant_view_is_distinct_from_an_actual_stop(self):
        route = self.official('杭州西湖')
        self.assertEqual(route['steps'][4]['poi'], '三潭印月')
        self.assertEqual(route['steps'][4]['visit_mode'], 'distant_view')

    def test_jiuzhaigou_period_hierarchy_and_shared_time_window(self):
        route = self.official('九寨沟')
        self.assertEqual(len(route['steps']), 15)
        self.assertEqual([p['time_period'] for p in route['hierarchy'][0]['periods']], ['上午', '中午', '下午'])
        step = route['steps'][12]
        self.assertEqual(step['clock_range_minutes'], [940, 1020])
        self.assertEqual(len(step['pois']), 7)
        self.assertEqual(step['visit_duration_text'], '约1个多小时')
        self.assertTrue(all('time_text' not in p for p in step['pois']))

    def test_visit_and_travel_durations_are_distinct(self):
        step = self.official('九寨沟')['steps'][1]
        self.assertEqual(step['visit_duration_text'], '20分钟')
        self.assertEqual(step['travel_duration_text'], '步行30分钟')
        self.assertEqual(step['clock_range_minutes'], [490, 540])

    def test_overlapping_source_times_remain_visible(self):
        route = self.official('九寨沟')
        self.assertEqual(route['steps'][-1]['time_text'], '17:00-17：35')
        issue = next(i for i in route['issues'] if i['code'] == 'overlapping_time_ranges')
        self.assertEqual(issue['step_ids'], [14, 15])

    def test_multi_day_hierarchy_and_surrounding_pois(self):
        route = self.official('九寨沟', 2)
        self.assertEqual([d['day'] for d in route['hierarchy']], [1, 2, 3])
        first_day = [p for s in route['steps'] if s['day'] == 1 for p in s['pois']]
        self.assertEqual([p['name'] for p in first_day], ['九寨沟县城', '九寨沟神仙池景区', '漳扎镇'])
        self.assertTrue(all(p['scope'] == 'surrounding' for p in first_day))
        self.assertNotIn('青龙海', [p['name'] for s in route['steps'] for p in s['pois']])

    def test_alias_mapping_does_not_merge_parent_child_or_theme(self):
        route = self.official('九寨沟', 1)
        swan = next(p for s in route['steps'] for p in s['pois'] if p['text'] == '天鹅湖')
        self.assertEqual(swan['name'], '天鹅海')
        compared = comparisons(self.officials, self.visitors)
        xihu = next(c for c in compared if c['scenic_spot'] == '杭州西湖')
        self.assertIn('雷峰夕照', xihu['normalized']['official_only'])
        self.assertIn('雷峰塔', xihu['normalized']['visitor_only'])

    def test_visitor_sample_scope_and_source_kind(self):
        self.assertEqual([r['route_kind'] for r in self.visitors], ['visitor_recommendation', 'visitor_recommendation', 'visitor_actual', 'visitor_actual', 'visitor_actual', 'visitor_actual'])
        actual = self.visitors[2]
        self.assertEqual(len(actual['steps']), 16)
        self.assertEqual(actual['steps'][0]['time_text'], '10：00')
        self.assertEqual(actual['steps'][-1]['time_text'], '17：45')
        self.assertNotIn('黄龙九寨站', sequence(actual))
        self.assertNotIn('诺日朗', sequence(actual))

    def test_ner_misses_can_be_recovered_from_official_route_nodes(self):
        doc = next(d for d in self.docs if d['scenic_spot'] == '北京故宫' and d['text_type'] == 'official_route')
        self.assertEqual(sequence(parse_gugong(doc, [])[0]), sequence(self.official('北京故宫')))

    def test_actual_route_retains_return_visits(self):
        seq = sequence(self.visitors[2])
        self.assertEqual(seq.count('原始森林'), 1)
        self.assertEqual(seq.count('树正瀑布'), 1)
        # Nonadjacent revisits are not globally removed by the sequence function.
        route = copy.deepcopy(self.official('北京故宫'))
        route['steps'].append(copy.deepcopy(route['steps'][0]))
        self.assertEqual(sequence(route).count('午门'), 2)

    def test_metrics_detect_order_reversal_and_different_coverage(self):
        result = metrics(['甲', '乙', '丙'], ['丙', '乙', '甲', '丁'])
        self.assertEqual(result['official_coverage'], 1)
        self.assertEqual(result['poi_jaccard'], 0.75)
        self.assertEqual(result['lcs_length'], 1)
        self.assertAlmostEqual(result['order_similarity'], 2 / 7)
        self.assertEqual(lcs_length([], ['甲']), 0)

    def test_all_provenance_slices_and_hierarchy_consistency(self):
        self.assertGreater(validate(self.officials + self.visitors, self.docs), 600)

    def test_wrong_offsets_and_missing_hierarchy_are_rejected(self):
        with self.assertRaises(ValueError):
            check_evidence({'text': '午门', 'start': 1, 'end': 3}, '午门前')
        route = copy.deepcopy(self.official('北京故宫'))
        route['hierarchy'][0]['periods'][0]['step_ids'].pop()
        with self.assertRaises(ValueError):
            validate([route], self.docs)

    def test_unicode_offsets_and_parenthesis_separators(self):
        doc = {'doc_id': 'test', 'scenic_spot': '杭州西湖', 'source_type': 'official', 'url': 'local', 'clean_text': '🌿甲文化之旅\n途径：法镜寺（下天竺—古称）—法喜寺\n'}
        route = parse_xihu(doc, [])[0]
        add_hierarchy(route)
        self.assertEqual([s['poi'] for s in route['steps']], ['法镜寺', '法喜寺'])
        validate([route], [doc])

    def test_three_way_comparison_and_elapsed_time(self):
        compared = comparisons(self.officials, self.visitors)
        self.assertEqual(len(compared), 6)
        self.assertEqual(compared[0]['normalized']['official_coverage'], 1)
        self.assertEqual(compared[1]['normalized']['official_coverage'], 0.5)
        self.assertEqual(compared[2]['time_comparison']['official_elapsed_minutes'], 635)
        self.assertEqual(compared[2]['time_comparison']['visitor_elapsed_minutes'], 465)
        self.assertEqual(compared[2]['time_comparison']['visitor_explicit_visit_durations'], 0)

    def test_self_reported_samples_have_source_evidence(self):
        by_id = {d['doc_id']: d for d in self.docs}
        for route in self.visitors:
            if route['route_kind'] == 'visitor_actual':
                proof = route['experience_evidence']
                self.assertIn(proof['text'], by_id[route['doc_id']][proof['field']])
        self.assertEqual(self.visitors[4]['experience_evidence']['field'], 'title')
        broken = copy.deepcopy(self.visitors[4])
        broken['experience_evidence']['text'] = '不存在的实走证明'
        with self.assertRaises(ValueError):
            validate([broken], self.docs)

    def test_parenthetical_landmark_is_not_a_visit(self):
        route = self.visitors[4]
        self.assertEqual(len(route['steps']), 6)
        self.assertNotIn('太子湾公园', [p['text'] for s in route['steps'] for p in s['pois']])
        step = next(s for s in route['steps'] if s['poi'] == '花港观鱼')
        self.assertIn('对面就是太子湾公园', step['evidence']['text'])

    def test_collective_nodes_are_not_expanded_into_leaf_visits(self):
        palace = self.visitors[3]
        collective = next(p for s in palace['steps'] for p in s['pois'] if p['text'] == '三大殿')
        self.assertEqual(collective['kind'], 'collective')
        self.assertNotIn('三大殿', sequence(palace))
        self.assertFalse({'太和殿', '中和殿', '保和殿'} & set(sequence(palace)))
        tree_region = next(p for s in self.visitors[5]['steps'] for p in s['pois'] if p['text'] == '树正区域')
        self.assertEqual(tree_region['kind'], 'collective')

    def test_selected_main_chains_exclude_warnings_and_repeated_highlights(self):
        route = self.visitors[5]
        text = next(d['clean_text'] for d in self.docs if d['doc_id'] == route['doc_id'])
        spans = [(text.index(line), text.index(line) + len(line)) for line in route['selection']['include_lines']]
        self.assertEqual(len(spans), 5)
        self.assertTrue(all(any(a <= s['evidence']['start'] < s['evidence']['end'] <= b for a, b in spans) for s in route['steps']))
        self.assertFalse(any('不建议' in s['evidence']['text'] or '尤其推荐' in s['evidence']['text'] for s in route['steps']))
        self.assertEqual(sequence(route).count('箭竹海'), 1)
        self.assertEqual(route['steps'][0]['pois'][0]['kind'], 'boundary')

    def test_missing_selected_line_fails_instead_of_silently_shortening_route(self):
        selection = copy.deepcopy(self.visitors[5]['selection'])
        selection['include_lines'].append('原文中不存在的行程链')
        with self.assertRaises(ValueError):
            visitor_routes(self.docs, self.entities, self.officials, [selection])

    def test_added_samples_do_not_invent_clock_periods_or_dates(self):
        added = self.visitors[3:]
        self.assertTrue(all(s['time_period'] is None for r in added for s in r['steps']))
        self.assertTrue(all(s['day'] is None for r in added[:2] for s in r['steps']))
        self.assertEqual(sum(s['time_period'] is not None for r in self.officials + self.visitors for s in r['steps']), 31)


if __name__ == '__main__':
    unittest.main()
