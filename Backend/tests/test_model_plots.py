from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from Backend.Benchmark.model_suite.reporting.plots import write_classification_plots


class ModelPlotTests(unittest.TestCase):
    def test_writes_confusion_and_one_vs_rest_curves_from_saved_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_classification_plots(
                y_true=[0, 1, 2, 0, 1, 2],
                y_pred=[0, 1, 1, 0, 2, 2],
                probabilities=[
                    [0.8, 0.1, 0.1],
                    [0.1, 0.7, 0.2],
                    [0.2, 0.3, 0.5],
                    [0.6, 0.2, 0.2],
                    [0.1, 0.4, 0.5],
                    [0.1, 0.2, 0.7],
                ],
                class_names=["REF", "HUM", "OTHER"],
                output_dir=Path(temp_dir),
                partition="test",
            )
            self.assertEqual([path.name for path in paths], ["confusion_matrix_test.png", "roc_pr_curves_test.png"])
            self.assertTrue(all(path.is_file() and path.stat().st_size > 0 for path in paths))

    def test_writes_confusion_only_when_probabilities_are_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = write_classification_plots(
                y_true=[0, 1],
                y_pred=[0, 0],
                probabilities=None,
                class_names=["REF", "HUM"],
                output_dir=Path(temp_dir),
                partition="test",
            )
            self.assertEqual([path.name for path in paths], ["confusion_matrix_test.png"])


if __name__ == "__main__":
    unittest.main()
