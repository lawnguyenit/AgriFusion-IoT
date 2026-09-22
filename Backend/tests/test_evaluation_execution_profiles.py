from pathlib import Path
import tempfile
import unittest

from Backend.Benchmark.evaluation_protocols.execution_profiles import EvaluationExecutionProfile


class EvaluationExecutionProfileTests(unittest.TestCase):
    def test_rq1_profile_is_e1_only(self) -> None:
        path = Path("Backend/Benchmark/evaluation_protocols/profiles/rq1_e1_only.yaml")
        profile = EvaluationExecutionProfile.load(path)
        self.assertEqual(profile.profile_id, "RQ1_E1_ONLY_V1")
        self.assertEqual(profile.read_environment_ids, ("E1",))
        self.assertEqual(profile.target_environment_ids, ())

    def test_future_profiles_keep_scope_explicit(self) -> None:
        root = Path("Backend/Benchmark/evaluation_protocols/profiles")
        rq2a = EvaluationExecutionProfile.load(root / "rq2a_e1_e2_source_expansion.yaml")
        rq2b = EvaluationExecutionProfile.load(root / "rq2b_e1_e2_to_e3.yaml")
        self.assertEqual(rq2a.read_environment_ids, ("E1", "E2"))
        self.assertEqual(rq2b.target_environment_ids, ("E3_TARGET_PREEXPOSED",))

    def test_target_scope_must_be_a_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.yaml"
            path.write_text(
                "profile_id: INVALID\n"
                "protocol_stage_id: CONTRACT_FROZEN\n"
                "label_apply_environment_ids: [E1]\n"
                "train_environment_ids: [E1]\n"
                "evaluation_environment_ids: [E1]\n"
                "target_environment_ids: E1\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                EvaluationExecutionProfile.load(path)


if __name__ == "__main__":
    unittest.main()
