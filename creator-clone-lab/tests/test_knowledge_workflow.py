from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import json
import os
from pathlib import Path


SKILL = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from capture_manifest import canonical_public_url
from knowledge_store import connect_db


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


class KnowledgeWorkflowTest(unittest.TestCase):
    def test_public_url_removes_signed_query_data(self) -> None:
        original = "https://www.xiaohongshu.com/explore/abc123?xsec_token=secret&xsec_source=pc_feed"
        self.assertEqual(canonical_public_url(original), "https://www.xiaohongshu.com/explore/abc123")

    def test_evidence_backed_search(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            body = root / "source.md"
            body.write_text("开头先展示完成结果，再解释处理流程。", encoding="utf-8")

            run_script(
                "init_creator_project.py",
                str(project),
                "--name",
                "test-project",
                "--creator",
                "test-creator",
                "--platform",
                "douyin",
            )
            run_script(
                "register_source.py",
                str(project),
                "--platform",
                "douyin",
                "--content-type",
                "video",
                "--creator",
                "test-creator",
                "--url",
                "https://example.com/1",
                "--title",
                "result-first",
                "--body-file",
                str(body),
                "--understanding-level",
                "full",
                "--source-id",
                "DY-TEST-001",
                "--metric",
                "views=1000",
            )
            run_script(
                "add_knowledge_atom.py",
                str(project),
                "--type",
                "HOK",
                "--title",
                "result-first-hook",
                "--statement",
                "工具内容先展示结果，再解释流程。",
                "--source-id",
                "DY-TEST-001",
                "--evidence-item",
                "DY-TEST-001|00:00-00:04|ASR+visual|先展示结果",
            )
            run_script(
                "add_knowledge_atom.py",
                str(project),
                "--type",
                "SOL",
                "--title",
                "无字幕视频转写",
                "--statement",
                "视频没有平台字幕时执行语音转写并结合画面文字。",
                "--source-id",
                "DY-TEST-001",
                "--evidence-item",
                "DY-TEST-001|00:05-00:10|ASR+visual|无字幕时补充语音转写",
            )
            result = run_script("query_knowledge.py", str(project), "展示结果")
            self.assertIn("DY-TEST-001", result.stdout)
            self.assertIn("00:00-00:04", result.stdout)
            self.assertIn("工具内容先展示结果", result.stdout)
            chinese_result = run_script("query_knowledge.py", str(project), "视频没有字幕怎么办")
            self.assertIn("无字幕视频转写", chinese_result.stdout)

    def test_manifest_to_clone_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            capture = root / "capture"
            capture.mkdir()
            (capture / "normalized.md").write_text("先展示结果，再解释自动处理流程。", encoding="utf-8")
            manifest = {
                "schema_version": "1.0",
                "platform": "douyin",
                "creator": "test-creator",
                "capture_kind": "single-video",
                "captured_at": "2026-07-12T00:00:00+08:00",
                "items": [
                    {
                        "source_id": "DY-TEST-002",
                        "platform": "douyin",
                        "creator": "test-creator",
                        "content_type": "video",
                        "url": "https://example.com/2",
                        "title": "result-first-demo",
                        "published_at": "2026-07-12T00:00:00+08:00",
                        "local_path": "",
                        "body_path": "normalized.md",
                        "understanding_level": "full",
                        "metrics": {"views": 2000, "saves": 100},
                    }
                ],
            }
            manifest_path = capture / "capture_manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            atoms = [
                {
                    "id": "HOK-TEST-001",
                    "type": "HOK",
                    "title": "result-first",
                    "statement": "工具内容先展示结果，再解释流程。",
                    "topics": ["tool-content"],
                    "confidence": "high",
                    "status": "pattern",
                    "performance_segment": "high-save",
                    "source_ids": ["DY-TEST-002"],
                    "evidence": [
                        {
                            "source_id": "DY-TEST-002",
                            "location": "00:00-00:04",
                            "modality": "ASR+visual",
                            "excerpt": "先展示结果",
                        },
                        {
                            "source_id": "DY-TEST-002",
                            "location": "00:04-00:08",
                            "modality": "visual",
                            "excerpt": "再解释处理流程",
                        }
                    ],
                    "raw_atom_ids": ["ATM-TEST-001", "ATM-TEST-002"],
                    "relationships": [{"type": "follows", "target": "HOK-TEST-002"}],
                },
                {
                    "id": "HOK-TEST-002",
                    "type": "HOK",
                    "title": "result-before-process",
                    "statement": "工具内容先展示完成结果，然后解释处理流程。",
                    "topics": ["tool-content"],
                    "confidence": "medium",
                    "status": "hypothesis",
                    "source_ids": ["DY-TEST-002"],
                    "raw_atom_ids": ["ATM-TEST-002"],
                    "evidence": [
                        {
                            "source_id": "DY-TEST-002",
                            "location": "00:04-00:08",
                            "modality": "visual",
                            "excerpt": "再解释处理流程",
                        }
                    ],
                },
            ]
            atom_path = root / "atoms.jsonl"
            atom_path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in atoms), encoding="utf-8")
            raw_atoms = [
                {
                    "id": "ATM-TEST-001",
                    "knowledge": "先展示结果",
                    "original": "先展示结果",
                    "source_id": "DY-TEST-002",
                    "source_locator": "00:00-00:04",
                    "topics": ["tool-content"],
                    "type": "hook",
                    "confidence": "high",
                    "status": "fact",
                },
                {
                    "id": "ATM-TEST-002",
                    "knowledge": "再解释处理流程",
                    "original": "再解释处理流程",
                    "source_id": "DY-TEST-002",
                    "source_locator": "00:04-00:08",
                    "topics": ["tool-content"],
                    "type": "structure",
                    "confidence": "high",
                    "status": "fact",
                },
            ]
            raw_atom_path = root / "raw_atoms.jsonl"
            raw_atom_path.write_text(
                "\n".join(json.dumps(item, ensure_ascii=False) for item in raw_atoms), encoding="utf-8"
            )

            run_script("init_creator_project.py", str(project), "--name", "pipeline", "--creator", "test-creator")
            run_script("import_capture_manifest.py", str(project), str(manifest_path))
            run_script("import_raw_atom_batch.py", str(project), str(raw_atom_path))
            run_script("import_atom_batch.py", str(project), str(atom_path))
            run_script("generate_duplicate_candidates.py", str(project), "--threshold", "0.60")
            run_script("generate_relation_map.py", str(project))
            run_script("generate_topic_maps.py", str(project))
            clone_result = run_script("build_creator_clone.py", str(project))
            run_script("prepare_atom_extraction.py", str(project), "--limit", "3")
            run_script("assemble_topic.py", str(project), "--topic", "tool-content", "--title", "new-tool-video")
            run_script(
                "record_performance.py",
                str(project),
                "DY-TEST-002",
                "--observed-at",
                "2026-07-12T01:00:00+08:00",
                "--stage",
                "T+1h",
                "--metric",
                "views=2000",
                "--metric",
                "likes=100",
            )
            run_script(
                "record_performance.py",
                str(project),
                "DY-TEST-002",
                "--observed-at",
                "2026-07-13T00:00:00+08:00",
                "--stage",
                "T+24h",
                "--metric",
                "views=5000",
                "--metric",
                "likes=280",
            )
            run_script("generate_retrospective.py", str(project), "DY-TEST-002")
            run_script("build_obsidian_vault.py", str(project))
            vault = project / "内容资产工程"
            unit_file = next((vault / "02-内容单元库" / "创作模式单元" / "开头模式").glob("HOK-TEST-001_*.md"))
            unit_text = unit_file.read_text(encoding="utf-8")
            first_evidence = next(line for line in unit_text.splitlines() if "@ `00:00-00:04`" in line)
            second_evidence = next(line for line in unit_text.splitlines() if "@ `00:04-00:08`" in line)
            self.assertIn("ATM-TEST-001", first_evidence)
            self.assertNotIn("ATM-TEST-002", first_evidence)
            self.assertIn("ATM-TEST-002", second_evidence)
            self.assertNotIn("ATM-TEST-001", second_evidence)

            run_script("render_obsidian_graph.py", str(vault))
            manual_note = vault / "08-人工笔记" / "人工研究.md"
            manual_note.write_text(f"# 人工研究\n\n[[{unit_file.stem}]]\n", encoding="utf-8")
            unit_file.write_text(unit_text + "\n人工修改必须被备份。\n", encoding="utf-8")
            run_script("build_obsidian_vault.py", str(project))
            vault_validation = json.loads(
                run_script("validate_obsidian_vault.py", str(vault)).stdout
            )
            status = json.loads(run_script("project_status.py", str(project)).stdout)

            self.assertIn("quick-analysis-only", clone_result.stdout)
            self.assertTrue((project / "06_topic_maps" / "tool-content.md").exists())
            self.assertTrue((project / "07_creator_clone" / "creator_clone.md").exists())
            self.assertTrue((project / "10_state" / "atom_extraction_jobs.jsonl").exists())
            self.assertEqual(len(list((project / "08_creations" / "assemblies").glob("*.md"))), 1)
            self.assertEqual(len(list((project / "11_reports").glob("retrospective_*.md"))), 1)
            relation_report = json.loads((project / "10_state" / "relation_index.json").read_text(encoding="utf-8"))
            self.assertEqual(relation_report["missing_target_count"], 0)
            duplicate_report = json.loads(
                (project / "10_state" / "duplicate_candidates.json").read_text(encoding="utf-8")
            )
            self.assertGreaterEqual(duplicate_report["candidate_count"], 1)
            self.assertEqual(status["clone_maturity"], "quick-analysis-only")
            self.assertGreaterEqual(status["duplicate_candidates"], 1)
            self.assertEqual(status["missing_relation_targets"], 0)
            self.assertEqual(status["performance_snapshot_count"], 2)
            self.assertEqual(status["retrospective_count"], 1)
            self.assertTrue(vault_validation["valid"])
            self.assertEqual(vault_validation["unresolved_links"], 0)
            self.assertEqual(vault_validation["duplicate_stems"], 0)
            self.assertEqual(vault_validation["orphan_nodes"], 0)
            self.assertEqual(vault_validation["modified_generated_files"], [])
            self.assertTrue((vault / ".obsidian" / "workspace.json").exists())
            self.assertTrue((vault / "03-处理状态" / "关系图谱预览.png").exists())
            self.assertTrue(manual_note.exists())
            self.assertNotIn("人工修改必须被备份", unit_file.read_text(encoding="utf-8"))
            backups = list((project / "10_state" / "vault_backups").rglob("*.md"))
            self.assertTrue(
                any("人工修改必须被备份" in path.read_text(encoding="utf-8") for path in backups)
            )
            marker = json.loads((vault / ".creator-clone-vault.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["schema_version"], "2.0")
            self.assertGreater(len(marker["generated_files"]), 0)

    def test_jsonl_atom_store_scales_and_searches_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            body = root / "source.md"
            body.write_text("批量知识原子来源。", encoding="utf-8")
            run_script("init_creator_project.py", str(project), "--name", "atom-scale", "--creator", "tester")
            run_script(
                "register_source.py",
                str(project),
                "--platform",
                "local",
                "--content-type",
                "other",
                "--title",
                "scale-source",
                "--body-file",
                str(body),
                "--understanding-level",
                "full",
                "--source-id",
                "SRC-SCALE-001",
            )
            atoms = []
            for index in range(1200):
                month = (index % 12) + 1
                knowledge = "视频没有字幕时执行语音转写" if index == 777 else f"批量知识原子 {index}"
                atoms.append(
                    {
                        "id": f"ATM-SCALE-{index:04d}",
                        "knowledge": knowledge,
                        "original": f"来源片段 {index}",
                        "source_id": "SRC-SCALE-001",
                        "source_locator": f"paragraph-{index}",
                        "date": f"2025-{month:02d}-01",
                        "topics": ["scale-test"],
                        "skills": ["creator-clone-lab"],
                        "type": "observation",
                        "confidence": "medium",
                        "status": "fact",
                    }
                )
            atom_file = root / "atoms.jsonl"
            atom_file.write_text(
                "".join(json.dumps(atom, ensure_ascii=False) + "\n" for atom in atoms), encoding="utf-8"
            )
            result = json.loads(run_script("import_raw_atom_batch.py", str(project), str(atom_file)).stdout)
            self.assertEqual(result["atom_count"], 1200)
            self.assertEqual(result["shard_count"], 4)
            query = run_script("query_raw_atoms.py", str(project), "视频没有字幕怎么办")
            self.assertIn("ATM-SCALE-0777", query.stdout)
            run_script(
                "add_knowledge_atom.py",
                str(project),
                "--type",
                "SOL",
                "--title",
                "无字幕视频处理",
                "--statement",
                "无字幕视频需要语音转写。",
                "--source-id",
                "SRC-SCALE-001",
                "--raw-atom-id",
                "ATM-SCALE-0777",
                "--atom-id",
                "SOL-SCALE-001",
            )
            aggregate = (project / "03_atom_store" / "atoms.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(aggregate), 1200)
            promoted = next(json.loads(line) for line in aggregate if '"ATM-SCALE-0777"' in line)
            self.assertEqual(promoted["unit_ids"], ["SOL-SCALE-001"])
            self.assertTrue((project / "04_content_units" / "SOL-SCALE-001_无字幕视频处理.md").exists())
            run_script("build_obsidian_vault.py", str(project))
            vault_validation = json.loads(
                run_script("validate_obsidian_vault.py", str(project / "内容资产工程")).stdout
            )
            self.assertTrue(vault_validation["valid"])
            self.assertGreaterEqual(vault_validation["markdown_nodes"], 1200)
            self.assertGreaterEqual(vault_validation["resolved_edges"], 1200)

    def test_resumable_processing_and_review_queue(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            run_script("init_creator_project.py", str(project), "--name", "queue", "--creator", "tester")
            for index in (1, 2):
                body = root / f"source-{index}.md"
                body.write_text("观众先看到结果，再理解解决步骤。", encoding="utf-8")
                run_script(
                    "register_source.py",
                    str(project),
                    "--platform", "local",
                    "--content-type", "article",
                    "--title", f"source-{index}",
                    "--body-file", str(body),
                    "--understanding-level", "full",
                    "--source-id", f"SRC-QUEUE-00{index}",
                )

            synced = json.loads(run_script("processing_queue.py", str(project), "sync").stdout)
            self.assertEqual(synced["statuses"], {"pending": 2})
            raw_ids = []
            for index in (1, 2):
                claimed = json.loads(
                    run_script("processing_queue.py", str(project), "claim", "--limit", "1").stdout
                )
                self.assertEqual(claimed["claimed"], 1)
                manifest = json.loads(Path(claimed["manifest"]).read_text(encoding="utf-8"))
                source_id = manifest["jobs"][0]["source_id"]
                raw_id = f"ATM-QUEUE-00{index}"
                raw_ids.append(raw_id)
                atoms_path = root / f"batch-{index}.jsonl"
                atoms_path.write_text(
                    json.dumps(
                        {
                            "id": raw_id,
                            "knowledge": "先展示明确结果，再解释解决步骤",
                            "original": "观众先看到结果，再理解解决步骤。",
                            "source_id": source_id,
                            "source_locator": "paragraph-1",
                            "topics": ["result-first"],
                            "type": "solution",
                            "confidence": "high",
                            "status": "fact",
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                completed = json.loads(
                    run_script(
                        "processing_queue.py",
                        str(project),
                        "complete",
                        "--batch-id", claimed["batch_id"],
                        "--atoms", str(atoms_path),
                    ).stdout
                )
                self.assertEqual(completed["completed_jobs"], 1)
            queue_status = json.loads(run_script("processing_queue.py", str(project), "status").stdout)
            self.assertEqual(queue_status["statuses"], {"completed": 2})

            run_script(
                "add_knowledge_atom.py",
                str(project),
                "--type", "QST",
                "--title", "如何让观众快速理解",
                "--statement", "观众需要先看到明确结果。",
                "--topic", "result-first",
                "--source-id", "SRC-QUEUE-001",
                "--raw-atom-id", raw_ids[0],
                "--atom-id", "QST-QUEUE-001",
            )
            run_script(
                "add_knowledge_atom.py",
                str(project),
                "--type", "SOL",
                "--title", "先结果后步骤",
                "--statement", "先展示明确结果，再解释解决步骤。",
                "--topic", "result-first",
                "--source-id", "SRC-QUEUE-002",
                "--raw-atom-id", raw_ids[1],
                "--atom-id", "SOL-QUEUE-001",
            )
            atom_candidates = json.loads(
                run_script("generate_atom_candidates.py", str(project), "--duplicate-threshold", "0.80").stdout
            )
            self.assertGreaterEqual(atom_candidates["duplicate_candidates"], 1)
            self.assertGreaterEqual(atom_candidates["promotion_candidates"], 1)
            relation_candidates = json.loads(
                run_script("generate_relation_candidates.py", str(project), "--threshold", "0.50").stdout
            )
            self.assertGreaterEqual(relation_candidates["relation_candidates"], 1)
            built = json.loads(run_script("review_queue.py", str(project), "build").stdout)
            self.assertGreaterEqual(built["statuses"].get("pending", 0), 3)
            review_items = [
                json.loads(line)
                for line in (project / "10_state" / "review_queue.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            relation_review = next(item for item in review_items if item["kind"] == "relation")
            promotion_review = next(item for item in review_items if item["kind"] == "promotion")
            run_script(
                "review_queue.py",
                str(project),
                "decide",
                relation_review["review_id"],
                "--decision", "accept",
                "--note", "关系证据成立",
            )
            run_script(
                "review_queue.py",
                str(project),
                "decide",
                promotion_review["review_id"],
                "--decision", "accept",
                "--title", "结果优先解决方案",
                "--statement", "跨来源重复证明应先展示结果再解释步骤。",
            )
            conn = connect_db(project / "index" / "knowledge.sqlite")
            try:
                relation_row = conn.execute(
                    "SELECT relationships_json FROM atoms WHERE atom_id = 'SOL-QUEUE-001'"
                ).fetchone()
                self.assertIn("QST-QUEUE-001", relation_row["relationships_json"])
                self.assertEqual(conn.execute("SELECT COUNT(*) FROM atoms").fetchone()[0], 3)
            finally:
                conn.close()
            maintenance = json.loads(run_script("run_batch_maintenance.py", str(project)).stdout)
            self.assertGreaterEqual(maintenance["step_count"], 10)
            self.assertTrue((project / "内容资产工程" / "03-处理状态" / "待审核队列.md").exists())
            decision_rows = (project / "10_state" / "review_decisions.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(decision_rows), 2)


if __name__ == "__main__":
    unittest.main()
