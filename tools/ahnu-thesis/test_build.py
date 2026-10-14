import unittest
from build import (main_tex, tex_escape, validate_source, wrap_identifiers,
                   format_references, superscript_citations)


class BuildTests(unittest.TestCase):
    def test_order_and_single_appendix(self):
        tex = main_tex(7)
        self.assertEqual(tex.count(r'\input{extraTex/body/appendix.tex}'), 1)
        self.assertNotIn('chapter-08', tex)
        self.assertLess(tex.index(r'\chapter*{致谢}'), tex.index(r'\ahnuReferencesHeading'))
        self.assertLess(tex.index(r'\ahnuReferencesHeading'), tex.index(r'\input{extraTex/body/appendix.tex}'))
        self.assertNotIn('signature.tex', tex)
        self.assertIn(r'\BenszThesisSetup{template=thesis-ahnu-master}', tex)

    def test_reject_silent_section_loss(self):
        base = '\n'.join('## '+s for s in ['摘要','Abstract','第一章 绪论','致谢','参考文献'])
        self.assertEqual(len(validate_source(base)), 1)
        for extra in ['\n## 摘要','\n## 未映射章节','\n## 第三章 跳章']:
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_source(base+extra)

    def test_identifier_breaks_preserve_text(self):
        value = r'\texttt{experiment\_\allowbreak{}notes.status}'
        result = wrap_identifiers(value)
        self.assertEqual(result.replace(r'\allowbreak{}',''), value.replace(r'\allowbreak{}',''))

    def test_metadata_is_plain_text(self):
        self.assertEqual(tex_escape('A&B_1%'), r'A\&B\_1\%')
        self.assertEqual(tex_escape(r'\input{x}'),r'\textbackslash{}input\{x\}')

    def test_reference_layout_preserves_entries(self):
        source = '{[}1{]} Author. Title{[}J{]}.\n\n{[}2{]} 第二篇.\n'
        result, count = format_references(source)
        self.assertEqual(count, 2)
        self.assertIn(r'\item[{[1]}] Author. Title{[}J{]}.', result)
        self.assertIn(r'\item[{[2]}] 第二篇.', result)
        with self.assertRaises(ValueError):
            format_references(source.replace('{[}2{]}', '{[}3{]}'))

    def test_superscripts_do_not_change_intervals_or_math(self):
        source = r'方法{[}1-3{]}；归一化{[}0,1{]}{[}118{]}。\([1,2]\)'
        self.assertEqual(superscript_citations(source, 118),
                         r'方法\textsuperscript{[1-3]}；归一化{[}0,1{]}\textsuperscript{[118]}。\([1,2]\)')


if __name__ == '__main__':
    unittest.main()
