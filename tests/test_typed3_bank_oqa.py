"""typed-v3 item bank, OfficeQA fixed code (skillopt/execskill/typed/bank/oqa.py): derivation checks, the anchor on
the reference answer, number twins and new-question checks. No model, no file, no network."""
import random
import unittest
from fractions import Fraction

from skillopt.execskill.typed.bank import oqa

DOC = """The following content is pre-parsed from the oracle OfficeQA source page(s).

### treasury_bulletin_1982_08.txt page 13

Tenders for the notes were received until 1:30 p.m. and totaled $10,102 million, of which $6,001 million was accepted.

| Item | 1981 | 1982 |
| --- | --- | --- |
| Total tenders | 9,455 | 10,102 |
| Accepted | 5,507 | 6,001 |
| Foreign accounts | 310.5 | 478.25 |
| Rate | 5.0 | 5.0 |
"""
QUESTION = ('How many dollars of tenders for the notes came in during 1982, and what percent of them was '
            'accepted? Round the second value to the nearest hundredths place.')
TRACE = {'values': [{'name': 'total', 'literal': '10,102', 'quote': 'totaled $10,102 million', 'kind': 'data'},
                    {'name': 'accepted', 'literal': '6,001', 'quote': 'of which $6,001 million was accepted', 'kind': 'data'},
                    {'name': 'year', 'literal': '1982', 'quote': '| Item | 1981 | 1982 |', 'kind': 'data'}],
         'answers': [{'expression': 'total * 1000000', 'decimals': 0},
                     {'expression': 'accepted / total * 100', 'decimals': 2}]}


def judge(prediction, gold):
    """A stand-in for the benchmark judge: the same numbers within 1e-9, part by part."""
    def parts(text):
        text = text.strip()
        body = text[1:-1].split(',') if text.startswith('[') else [text]
        return [Fraction(p.strip().replace(',', '')) for p in body]
    try:
        a, b = parts(prediction), parts(gold)
    except (ValueError, ZeroDivisionError):
        return False
    return len(a) == len(b) and all(abs(x - y) < Fraction(1, 10 ** 9) for x, y in zip(a, b))


class TraceTest(unittest.TestCase):
    def test_normal_form_keeps_used_values_and_marks_years(self):
        normal = oqa.check_trace(TRACE, DOC)
        self.assertEqual([v['name'] for v in normal['values']], ['total', 'accepted'])  # 'year' is used nowhere
        self.assertEqual(normal['values'][0]['occurrences'], 2)
        self.assertEqual(oqa.compute_answers(normal), ['10102000000', '59.40'])
        self.assertEqual(oqa.gold_text(['10102000000', '59.40']), '[10102000000, 59.40]')
        with_year = {'values': TRACE['values'], 'answers': [{'expression': 'total - year', 'decimals': None}]}
        kinds = {v['name']: v['kind'] for v in oqa.check_trace(with_year, DOC)['values']}
        self.assertEqual(kinds, {'total': 'data', 'year': 'selector'})

    def test_refusals(self):
        def reason(trace, doc=DOC):
            with self.assertRaises(oqa.Drop) as caught:
                oqa.check_trace(trace, doc)
            return caught.exception.reason
        self.assertEqual(reason({'not_numeric': True}), 'not_numeric')
        self.assertEqual(reason({'values': [], 'answers': []}), 'shape')
        one = lambda **kw: {'values': [{**TRACE['values'][0], **kw}], 'answers': [{'expression': 'total', 'decimals': 0}]}
        self.assertEqual(reason(one(literal='$10,102')), 'literal_unparsable')
        self.assertEqual(reason(one(quote='totaled $10,103 million')), 'quote_not_in_document')
        self.assertEqual(reason(one(literal='10,10')), 'literal_unparsable')
        self.assertEqual(reason(one(literal='102')), 'literal_not_in_quote')  # inside 10,102: not a whole token
        self.assertEqual(reason(one(name='sum')), 'value_name')
        bad = {'values': TRACE['values'][:1], 'answers': [{'expression': 'total + other', 'decimals': 0}]}
        self.assertEqual(reason(bad), 'unknown_name')
        bad = {'values': TRACE['values'][:1], 'answers': [{'expression': 'total +', 'decimals': 0}]}
        self.assertEqual(reason(bad), 'expression')
        bad = {'values': TRACE['values'][:1], 'answers': [{'expression': 'total', 'decimals': 7}]}
        self.assertEqual(reason(bad), 'decimals')
        bad = {'values': TRACE['values'][:1], 'answers': [{'expression': '3 * 4', 'decimals': 0}]}
        self.assertEqual(reason(bad), 'no_document_value')

    def test_a_document_number_written_as_a_constant_is_refused(self):
        def reason(expression):
            trace = {'values': TRACE['values'][:1], 'answers': [{'expression': expression, 'decimals': None}]}
            try:
                oqa.check_trace(trace, DOC)
            except oqa.Drop as refused:
                return refused.reason
        self.assertEqual(reason('total + 6001'), 'constant_from_document')       # printed as 6,001
        comma = {'values': TRACE['values'][:1], 'answers': [{'expression': 'total + 5,507', 'decimals': None}]}
        with self.assertRaises(oqa.Drop) as caught:                              # a comma inside an expression
            oqa.compute_answers(oqa.check_trace(comma, DOC))
        self.assertEqual(caught.exception.reason, 'expression')
        self.assertEqual(reason('total + 478.25'), 'constant_from_document')
        self.assertIsNone(reason('total * 1000000 / 100 + 12 + 5.0'))             # units, short constants
        self.assertIsNone(reason('total + 7777'))                                 # printed nowhere

    def test_quote_is_searched_with_squashed_whitespace(self):
        trace = {'values': [{'name': 'a', 'literal': '9,455', 'quote': '| Total tenders  |  9,455 |', 'kind': 'data'}],
                 'answers': [{'expression': 'a', 'decimals': None}]}
        self.assertEqual(oqa.compute_answers(oqa.check_trace(trace, DOC)), ['9455'])

    def test_exact_value_must_terminate(self):
        trace = {'values': TRACE['values'][:2], 'answers': [{'expression': 'accepted / total', 'decimals': None}]}
        with self.assertRaises(oqa.Drop) as caught:
            oqa.compute_answers(oqa.check_trace(trace, DOC))
        self.assertEqual(caught.exception.reason, 'not_terminating')

    def test_anchor(self):
        normal, computed = oqa.anchor(TRACE, DOC, '[10102000000, 59.4]', judge)
        self.assertEqual(computed, '[10102000000, 59.40]')
        with self.assertRaises(oqa.Drop) as caught:
            oqa.anchor(TRACE, DOC, '[10102000000, 4.73]', judge)
        self.assertEqual(caught.exception.reason, 'reference_not_reproduced')


class StatisticsTest(unittest.TestCase):
    """Derivations the first pass could not write down: steps, statistics, long sums, ties."""
    ROWS = "\n".join('| %d | %s |' % (1950 + i, v) for i, v in enumerate(['12.5', '14.25', '11.0', '17.75', '9.5', '21.0']))
    DOC3 = 'Note.\n\n### treasury_bulletin_1957_03.txt page 4\n\n| Year | Rate |\n| --- | --- |\n' + ROWS + '\n'

    def trace(self, steps, answers):
        literals = ['12.5', '14.25', '11.0', '17.75', '9.5', '21.0']
        values = [{'name': 'v%d' % i, 'literal': lit, 'quote': '| %d | %s |' % (1949 + i, lit)} for i, lit in enumerate(literals, 1)]
        return {'values': values, 'steps': steps, 'answers': answers}

    def test_steps_and_statistics_anchor(self):
        series = 'v1, v2, v3, v4, v5, v6'
        trace = self.trace([{'name': 'm', 'expression': 'mean(%s)' % series}, {'name': 'unused', 'expression': 'm * 2'}],
                           [{'expression': 'stdev_pop(%s) / m * 100' % series, 'decimals': 2},
                            {'expression': '(v6 / v1) ** (1 / 5) - 1', 'decimals': 4}])
        normal, computed = oqa.anchor(trace, self.DOC3, '[27.61, 0.1093]', oqa.officeqa_judge)
        self.assertEqual(computed, '[27.61, 0.1093]')
        self.assertEqual([s['name'] for s in normal['steps']], ['m'])                    # the unreached step is left out
        self.assertEqual(len(normal['values']), 6)
        self.assertEqual(oqa.features('Q?', computed, normal)['operations'], ['div', 'mean', 'mul', 'pow', 'stdev_pop', 'sub'])
        context, gold, changes = oqa.make_twin(self.DOC3, 'What is the coefficient of variation of the rate?', normal,
                                               computed, random.Random(4), oqa.officeqa_judge)
        self.assertNotEqual(gold, computed)
        self.assertEqual(len(changes), 6)                                                 # every value is data here
        sheet = oqa.rubric(normal)
        self.assertEqual(oqa.classify('[27.61, 0.10933]', sheet), 'rounding')
        self.assertEqual(oqa.classify('[0.2761, 0.1093]', sheet), 'percent_form')

    def test_refusals_of_steps(self):
        def reason(steps, answers):
            with self.assertRaises(oqa.Drop) as caught:
                oqa.compute_answers(oqa.check_trace(self.trace(steps, answers), self.DOC3))
            return caught.exception.reason
        self.assertEqual(reason([{'name': 'm', 'expression': 'mean(v1, later)'}, {'name': 'later', 'expression': 'v2'}],
                                [{'expression': 'm', 'decimals': 1}]), 'unknown_name')
        self.assertEqual(reason([{'name': 'v1', 'expression': 'v2'}], [{'expression': 'v1', 'decimals': 1}]), 'value_name')
        self.assertEqual(reason([{'name': 'sum', 'expression': 'v2'}], [{'expression': 'v1', 'decimals': 1}]), 'value_name')
        self.assertEqual(reason([], [{'expression': 'median(v1, v2) if v3 else v4', 'decimals': 1}]), 'expression')
        self.assertEqual(reason([], [{'expression': 'sqrt(v1 - v6)', 'decimals': 1}]), 'expression')
        self.assertEqual(reason([], [{'expression': 'sqrt(v1)', 'decimals': None}]), 'not_terminating')
        self.assertEqual(reason([{'name': 'm', 'expression': 'v1 + 17.75'}], [{'expression': 'm', 'decimals': 1}]),
                         'constant_from_document')

    def test_a_reference_written_at_an_exact_tie_is_reproduced_either_way(self):
        tie = self.trace([], [{'expression': 'v2 / 10', 'decimals': 2}])                  # 1.425
        for reference in ('1.43', '1.42'):
            self.assertEqual(oqa.anchor(tie, self.DOC3, reference, oqa.officeqa_judge)[1], reference)
        with self.assertRaises(oqa.Drop) as caught:                                        # a made answer may not be a tie
            oqa.check_rounding(oqa.check_trace(tie, self.DOC3))
        self.assertEqual(caught.exception.reason, 'rounding_tie')


class TwinTest(unittest.TestCase):
    def test_perturbed_literal_keeps_its_printed_form(self):
        rng = random.Random(7)
        for literal in ('10,102', '6,001', '478.25', '0.063', '37', '1,234,567.5'):
            for _ in range(50):
                new = oqa.perturb_literal(literal, rng)
                self.assertNotEqual(new, literal)
                self.assertTrue(oqa.LITERAL.fullmatch(new), new)
                self.assertEqual(len(new.partition('.')[2]), len(literal.partition('.')[2]))
                self.assertEqual(',' in new, ',' in literal and len(new.split('.')[0].replace(',', '')) > 3)
                ratio = Fraction(new.replace(',', '')) / Fraction(literal.replace(',', ''))
                self.assertTrue(Fraction(3, 4) < ratio < Fraction(5, 4), (literal, new))
        self.assertIsNone(oqa.perturb_literal('0.00', rng))

    def test_twin_replaces_every_occurrence_and_recomputes(self):
        normal, old_gold = oqa.anchor(TRACE, DOC, '[10102000000, 59.4]', judge)
        context, gold, changes = oqa.make_twin(DOC, QUESTION, normal, old_gold, random.Random(3), judge)
        self.assertEqual(set(changes), {'10,102', '6,001'})
        self.assertNotIn('10,102', context)
        self.assertEqual(context.count(changes['10,102']), 2)       # the sentence and the table row agree
        self.assertEqual(context.count(changes['6,001']), 2)
        self.assertIn('| 9,455 |', context)                         # untouched numbers stay
        self.assertEqual(gold, oqa.gold_text(oqa.compute_answers(normal, changes)))
        self.assertFalse(judge(old_gold, gold))
        self.assertEqual(len(context.splitlines()), len(DOC.splitlines()))

    def test_literals_that_must_not_change(self):
        # a literal named in the question, a selector's literal and a one-digit literal stay
        trace = {'values': [{'name': 'rate', 'literal': '5.0', 'quote': '| Rate | 5.0 | 5.0 |', 'kind': 'data'},
                            {'name': 'year', 'literal': '1982', 'quote': '| Item | 1981 | 1982 |', 'kind': 'data'}],
                 'answers': [{'expression': 'rate * 2 + year * 0', 'decimals': 1}]}
        normal = oqa.check_trace(trace, DOC)
        changes = oqa.choose_changes(normal, DOC, 'What is twice the rate?', random.Random(1))
        self.assertEqual(set(changes), {'5.0'})
        with self.assertRaises(oqa.Drop) as caught:
            oqa.choose_changes(normal, DOC, 'The rate was 5.0 percent; what is twice that?', random.Random(1))
        self.assertEqual(caught.exception.reason, 'nothing_to_change')
        only_year = {'values': trace['values'][1:], 'answers': [{'expression': 'year + 1', 'decimals': 0}]}
        with self.assertRaises(oqa.Drop) as caught:
            oqa.choose_changes(oqa.check_trace(only_year, DOC), DOC, QUESTION, random.Random(1))
        self.assertEqual(caught.exception.reason, 'no_data_value')

    def test_replacement_is_one_pass_and_token_wise(self):
        text = 'a 12 b 120 c 1,012 d 12.5 e 12'
        self.assertEqual(oqa.replace_literals(text, {'12': '120', '120': '7'}), 'a 120 b 7 c 1,012 d 12.5 e 120')

    def test_twin_whose_answer_does_not_change_is_refused(self):
        trace = {'values': [{'name': 'a', 'literal': '10,102', 'quote': 'totaled $10,102 million', 'kind': 'data'}],
                 'answers': [{'expression': 'a * 0 + 4', 'decimals': 0}]}
        normal, old = oqa.anchor(trace, DOC, '4', judge)
        with self.assertRaises(oqa.Drop) as caught:
            oqa.make_twin(DOC, QUESTION, normal, old, random.Random(2), judge)
        self.assertEqual(caught.exception.reason, 'answer_unchanged')


class NewQuestionTest(unittest.TestCase):
    PARENT = oqa.check_trace(TRACE, DOC)

    def entry(self, **kw):
        base = {'question': 'By how many million dollars did the tenders accepted for the 2-year notes rise from 1981 '
                            'to 1982, according to the table of tenders?',
                'values': [{'name': 'a', 'literal': '6,001', 'quote': '| Accepted | 5,507 | 6,001 |', 'kind': 'data'},
                           {'name': 'b', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |', 'kind': 'data'}],
                'answers': [{'expression': 'a - b', 'decimals': 0}], 'answer': '999'}
        return {**base, **kw}

    def check(self, entry, **kw):
        return oqa.check_new_question(entry, DOC, parent_question=QUESTION, parent_trace=self.PARENT, **kw)

    def test_answer_is_computed_never_taken(self):
        question, normal, gold = self.check(self.entry())
        self.assertEqual(gold, '494')

    def test_refusals(self):
        def reason(entry, **kw):
            with self.assertRaises(oqa.Drop) as caught:
                self.check(entry, **kw)
            return caught.exception.reason
        self.assertEqual(reason(self.entry(question='Too short?')), 'question_shape')
        self.assertEqual(reason(self.entry(question=QUESTION)), 'question_repeats_parent')
        same = self.entry(values=TRACE['values'][:2], answers=TRACE['answers'])
        self.assertEqual(reason(same), 'derivation_repeats_parent')
        kept = self.check(self.entry())
        self.assertEqual(reason(self.entry(), siblings=[(kept[0], kept[1])]), 'question_repeats_sibling')
        leak = self.entry(question=self.entry()['question'] + ' (The answer is 494 million.)')
        self.assertEqual(reason(leak), 'answer_in_question')
        constant = self.entry(values=[{'name': 'y', 'literal': '1982', 'quote': '| Item | 1981 | 1982 |'}],
                              answers=[{'expression': 'y - 1900', 'decimals': 0}])
        self.assertEqual(reason(constant), 'constant_answer')
        # a made answer never carries '%': a question that asks for the sign would refuse its own right answer
        share = {'question': 'What percent of the tenders accepted in 1982 had been accepted in 1981, to one decimal '
                             'place? Include the percent sign.', 'answers': [{'expression': 'b / a * 100', 'decimals': 1}]}
        self.assertEqual(reason(self.entry(**share)), 'percent_sign_asked')
        plain = self.entry(**{**share, 'question': share['question'].replace(' Include the percent sign.', '')})
        question, _, gold = self.check(plain)
        self.assertTrue(question.endswith('to one decimal place? ' + oqa.FORM_SENTENCES[0]) and gold == '91.8')

    def test_a_value_without_effect_and_fragile_rounding_are_refused(self):
        def reason(entry):
            with self.assertRaises(oqa.Drop) as caught:
                self.check(entry)
            return caught.exception.reason
        idle = self.entry(answers=[{'expression': 'a + b * 0', 'decimals': 0}])
        self.assertEqual(reason(idle), 'value_without_effect')
        zero = self.entry(answers=[{'expression': 'a / b * 100 - 8.97', 'decimals': 1}])       # 100.0
        self.assertEqual(reason(zero), 'trailing_zero')
        tie = self.entry(answers=[{'expression': '(a - b) / 8', 'decimals': 1}])               # 61.75
        self.assertEqual(reason(tie), 'rounding_tie')

    def test_features(self):
        row = oqa.features(QUESTION, '[10102000000, 59.40]', self.PARENT, DOC)
        self.assertEqual((row['answer_kind'], row['answer_parts'], row['rounding_stated'], row['pages']),
                         ('list', 2, True, 1))
        self.assertEqual(row['operations'], ['div', 'mul'])
        self.assertEqual(oqa.features('What?', '-75')['answer_kind'], 'integer')
        self.assertTrue(oqa.features('What?', '-75')['negative'])
        self.assertEqual(oqa.features('What?', 'March 3, 1977')['answer_kind'], 'text')


class DocumentBodyTest(unittest.TestCase):
    DOC2 = ('The following content is pre-parsed from the oracle OfficeQA source page(s). Treat it as evidence.\n\n'
            '### treasury_bulletin_1963_01.txt page 88\n'
            'Source URL: https://fraser.stlouisfed.org/title/treasury-bulletin-407/january-1963-6793?page=88\n\n'
            '| Year | Paper money |\n| --- | --- |\n| 1961 | 88 |\n| 1962 | 407 |\n')

    def test_headers_and_urls_never_count_or_change(self):
        self.assertEqual(oqa.count_tokens('88', self.DOC2), 1)
        self.assertEqual(oqa.count_tokens('407', self.DOC2), 1)
        changed = oqa.replace_literals(self.DOC2, {'88': '93', '407': '388'})
        self.assertIn('page 88\n', changed)
        self.assertIn('?page=88\n', changed)
        self.assertIn('treasury-bulletin-407/', changed)
        self.assertIn('| 1961 | 93 |', changed)
        self.assertIn('| 1962 | 388 |', changed)
        self.assertEqual(oqa.pages_of(self.DOC2), {('treasury_bulletin_1963_01.txt', 88)})

    def test_a_quote_from_a_header_line_is_refused(self):
        trace = {'values': [{'name': 'a', 'literal': '88', 'quote': 'treasury_bulletin_1963_01.txt page 88'}],
                 'answers': [{'expression': 'a', 'decimals': None}]}
        with self.assertRaises(oqa.Drop) as caught:
            oqa.check_trace(trace, self.DOC2)
        self.assertEqual(caught.exception.reason, 'quote_not_in_document')


class BenchmarkJudgeTest(unittest.TestCase):
    """The real comparison is string equality after normalisation: what a made answer must look like."""

    def test_the_benchmark_judge(self):
        j = oqa.officeqa_judge
        self.assertTrue(j('$1234.5 million', '1,234.5'))
        self.assertFalse(j('1234.50', '1234.5'))
        self.assertFalse(j('20.21', '20.21%'))
        self.assertTrue(j('[10102000000, 4.73]', '[10102000000, 4.73]'))
        self.assertFalse(j('[10102000000,4.73]', '[10102000000, 4.73]'))    # the blank separates the parts

    def test_percent_reference_gets_its_sign(self):
        trace = {'values': [{'name': 'a', 'literal': '6,001', 'quote': 'of which $6,001 million was accepted'},
                            {'name': 'b', 'literal': '10,102', 'quote': 'totaled $10,102 million'}],
                 'answers': [{'expression': 'a / b * 100', 'decimals': 1}]}
        normal, computed = oqa.anchor(trace, DOC, '59.4%', oqa.officeqa_judge)
        self.assertEqual((computed, normal['suffix']), ('59.4%', '%'))
        context, gold, changes = oqa.make_twin(DOC, 'What share of the tenders was accepted?', normal, computed,
                                               random.Random(5), oqa.officeqa_judge)
        self.assertTrue(gold.endswith('%') and not gold.endswith('0%'))
        with self.assertRaises(oqa.Drop):
            oqa.anchor(trace, DOC, '59.40%', oqa.officeqa_judge)             # a reference the digits cannot equal


class RubricTest(unittest.TestCase):
    NORMAL = oqa.check_trace({'values': TRACE['values'][:2],
                              'answers': [{'expression': 'accepted / total * 100', 'decimals': 2}]}, DOC)

    def test_rubric_holds_the_answer_and_the_coded_mistakes(self):
        sheet = oqa.rubric(self.NORMAL)
        self.assertEqual(sheet['exact'], [str(Fraction(600100, 10102))])
        self.assertEqual(sheet['read'], ['10102', '6001'])
        self.assertEqual([m['label'] for m in sheet['mistakes']], ['swapped_operands'])
        self.assertEqual(sheet['mistakes'][0]['values'], [str(Fraction(1010200, 6001))])
        named = {'label': 'adjacent_year', 'text': 'the 1981 column read for 1982', 'trace': oqa.check_trace(
            {'values': [{'name': 'accepted', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'},
                        {'name': 'total', 'literal': '9,455', 'quote': '| Total tenders | 9,455 | 10,102 |'}],
             'answers': [{'expression': 'accepted / total * 100', 'decimals': 2}]}, DOC)}
        sheet = oqa.rubric(self.NORMAL, mistakes=[named])
        self.assertEqual([m['label'] for m in sheet['mistakes']], ['swapped_operands', 'adjacent_year'])

    def test_labels_of_wrong_replies(self):
        named = {'label': 'adjacent_year', 'text': '', 'trace': oqa.check_trace(
            {'values': [{'name': 'accepted', 'literal': '5,507', 'quote': '| Accepted | 5,507 | 6,001 |'},
                        {'name': 'total', 'literal': '9,455', 'quote': '| Total tenders | 9,455 | 10,102 |'}],
             'answers': [{'expression': 'accepted / total * 100', 'decimals': 2}]}, DOC)}
        sheet = oqa.rubric(self.NORMAL, mistakes=[named])
        label = lambda text: oqa.classify(text, sheet)
        self.assertEqual(label('59.40'), 'format')               # right number, refused for how it is written
        self.assertEqual(label('59.4%'), 'format')
        self.assertEqual(label('59.404'), 'rounding')
        self.assertEqual(label('59'), 'rounding')
        self.assertEqual(label('0.59'), 'percent_form')
        self.assertEqual(label('0.594'), 'percent_form')
        self.assertEqual(label('59404.08'), 'unit_scale')
        self.assertEqual(label('-59.4'), 'sign')
        self.assertEqual(label('168.34'), 'swapped_operands')
        self.assertEqual(label('58.24'), 'adjacent_year')
        self.assertEqual(label('6,001'), 'read_not_computed')
        self.assertEqual(label('61.7'), 'other')
        self.assertEqual(label('no idea'), 'no_answer')
        self.assertEqual(label('[59.4, 3]'), 'part_count')

    def test_labels_of_a_two_part_answer(self):
        normal = oqa.check_trace(TRACE, DOC)
        sheet = oqa.rubric(normal)
        self.assertEqual(oqa.classify('[59.4, 10102000000]', sheet), 'order')
        self.assertEqual(oqa.classify('[10102, 59.4]', sheet), 'unit_scale')
        self.assertEqual(oqa.classify('[10102, 0.594]', sheet), 'unit_scale+percent_form')
        self.assertEqual(oqa.classify('[10102000000, 59.4]', sheet), 'format')


if __name__ == '__main__':
    unittest.main()


def test_replacing_many_literals_never_reads_what_it_wrote():
    # review 2026-11-13: eleven changes and the literal 10 -- the marker of change number 10 must not be rewritten
    changes = {str(1000 + n): str(1200 + n) for n in range(11)}
    changes['10'] = '13'
    context = '### file.pdf page 10\n' + ' | '.join(sorted(changes)) + ' | 10 units, 1,010 and 10.5 stay\nSource URL: x?page=10'
    made = oqa.replace_literals(context, changes).split('\n')
    assert made[0] == '### file.pdf page 10' and made[2] == 'Source URL: x?page=10'
    assert made[1] == ' | '.join(changes[old] for old in sorted(changes)) + ' | 13 units, 1,010 and 10.5 stay'
    swapped = oqa.replace_literals(context, {'1010': '10', '10': '1010'}).split('\n')[1]   # a swap, in one pass
    assert swapped.startswith('1010 | 1000 | 1001') and swapped.endswith('| 1009 | 10 | 1010 units, 1,010 and 10.5 stay')
    assert oqa.replace_literals(context, {}) == context


def test_what_a_question_says_about_the_percent_sign():
    assert oqa.percent_form('By how many million dollars did outlays rise?') == 'none'
    assert oqa.percent_form('By what percent did outlays rise? Round to one decimal place.') == 'add'
    assert oqa.percent_form('At the 5% significance level, what is the z-score, as a percent of the mean?') == 'add'
    for stated in ('Only report the value with no percent sign.', 'Give the percent change without commas or percent signs.',
                   'Report the share in percent, omitting the % symbol.'):
        assert oqa.percent_form(stated) == 'stated', stated
    for conflict in ('What percent was accepted? Include the percent sign.', 'Give the share with a % sign.',
                     'Report the percent change, no commas, and include the percent sign.',
                     'What percent was accepted (e.g., 12.34%)?', 'State the growth and the percent sign convention used.'):
        assert oqa.percent_form(conflict) == 'conflict', conflict


def test_form_sentence_for_percent_questions():
    one, several = oqa.FORM_SENTENCES
    assert oqa.form_sentence('By what percent did outlays rise from 1981 to 1982? Round to one decimal place.', 1) == one
    assert oqa.form_sentence('Give the total in millions and its share of receipts in %, in brackets.', 2) == several
    assert oqa.form_sentence('By what percent did outlays rise? Only report the value with no percent sign.', 1) == ''
    assert oqa.form_sentence('Report the percentage change without commas or percent signs.', 1) == ''
    assert oqa.form_sentence('By how many million dollars did outlays rise from 1981 to 1982?', 1) == ''


def test_a_coded_mistake_whose_rounding_is_not_settled_is_left_out_of_the_rubric():
    # second review 2026-11-13: the swapped derivation is exactly 5/2 - sqrt(4) = 0.5; its midpoint lies below one
    # half and would have been stored and rounded to 0
    from skillopt.execskill.typed.bank import calc
    trace = {'values': [{'name': 'a', 'literal': '5'}, {'name': 'b', 'literal': '4'}],
             'answers': [{'expression': 'b/2 - pow(a,0.5)', 'decimals': 0, 'names': ['a', 'b']}]}
    assert oqa.compute_answers(trace) == ['0']
    tie = oqa.swapped(trace)[('a', 'b')][0]
    assert isinstance(tie, calc.Approx) and calc.near_tie(tie, 0)
    assert oqa.rubric(trace)['mistakes'] == []
    plain = {'values': trace['values'], 'answers': [{'expression': 'b/2 - a', 'decimals': 0, 'names': ['a', 'b']}]}
    assert [m['label'] for m in oqa.rubric(plain)['mistakes']] == ['swapped_operands']
