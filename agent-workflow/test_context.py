import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
import agent_context as ctx


class ContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = Path(self.tmp.name)

    def project(self, name='샘플', **extra):
        meta = dict(project=name, status='active', done=False, summary='요약', next='실제 결과 확인',
                    updated='2026-10-01', agent='test', aliases=['별칭'])
        meta.update(extra)
        path = self.vault / '30_Projects' / name / '00 현재 상태.md'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('---\n' + yaml.safe_dump(meta, allow_unicode=True) + '---\n본문\n')
        return path

    def test_user_done_controls_visibility_and_alias_kept(self):
        self.project('완료', done=True, status='review')
        self.project('검토', status='done')
        rows = ctx.projects(self.vault)
        text = ctx.render(rows)
        self.assertNotIn('## 완료', text)
        self.assertIn('## 검토', text)
        self.assertTrue(ctx.resume(rows, '완료')[0]['done'])

    def test_byte_limit_and_no_omitted_projects(self):
        for i in range(12):
            self.project(f'긴 프로젝트 {i}', next='매우 긴 다음 행동입니다 ' * 100, aliases=['별칭도 길어요' * 20])
        rows = ctx.projects(self.vault)
        text = ctx.render(rows)
        self.assertLessEqual(len(text.encode()), 4096)
        self.assertEqual(text.count('\n## '), 12)
        with self.assertRaises(ValueError):
            ctx.render(rows, 100)

    def test_windows_line_endings_keep_user_completion_and_aliases(self):
        p = self.project('완료', done=True)
        p.write_bytes(b'\xef\xbb\xbf' + p.read_bytes().replace(b'\n', b'\r\n'))
        rows = ctx.projects(self.vault)
        self.assertFalse(rows[0]['legacy'])
        self.assertTrue(ctx.resume(rows, '별칭')[0]['done'])
        self.assertNotIn('## 완료', ctx.render(rows))

    def test_legacy_visible_and_bad_yaml_stops_generation(self):
        p = self.project()
        p.write_text('# 샘플\n갱신: 2026-10-01 Codex\n- 현재: 진행\n')
        (self.vault / '30_Projects/Index.md').write_text('| 🔥 | 샘플 프로젝트 | 다른 별명, CAVA | 정본 |\n')
        self.assertTrue(ctx.projects(self.vault)[0]['legacy'])
        self.assertEqual(len(ctx.resume(ctx.projects(self.vault), 'CAVA')), 1)
        self.assertIn('## 샘플', ctx.render(ctx.projects(self.vault)))
        p.write_text('---\naliases: [\n---\n')
        with self.assertRaises(yaml.YAMLError):
            ctx.projects(self.vault)

    def test_manual_edits_protected_and_migration_backed_up(self):
        self.project()
        p = self.vault / '00_System/Now.md'
        p.parent.mkdir(); original = '# 사람이 쓴 기존 보드\n'
        p.write_text(original)
        with self.assertRaises(ValueError):
            ctx.refresh(self.vault, 4096)
        self.assertEqual(p.read_text(), original)
        ctx.refresh(self.vault, 4096, hashlib.sha256(original.encode()).hexdigest())
        backup = list(p.parent.glob('Now 이전 보드 *.md'))
        self.assertEqual(len(backup), 1)
        self.assertEqual(backup[0].read_text(), original)
        self.assertTrue(ctx.managed(p.read_text()))
        self.assertFalse(ctx.refresh(self.vault, 4096)['changed'])
        p.write_text(p.read_text() + '다른 에이전트의 추가\n')
        with self.assertRaises(ValueError):
            ctx.refresh(self.vault, 4096)

    def test_changed_source_prevents_stale_publish(self):
        self.project()
        rows = ctx.projects(self.vault)
        changed = [dict(rows[0], sha256='different')]
        with patch.object(ctx, 'projects', side_effect=[rows, changed]):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                ctx.refresh(self.vault, 4096)
        self.assertFalse((self.vault / '00_System/Now.md').exists())


if __name__ == '__main__':
    unittest.main()
