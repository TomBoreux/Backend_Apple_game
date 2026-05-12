from django.test import SimpleTestCase

from .report_charts import full_reports_global_stats, full_report_stats
from .views import dat_report_payload, is_study_client_platform, new_report_blocks


VALID_LEVEL_BLOCK = "\n".join(
    [
        "42",
        "12.5",
        "0 0",
        "5 5",
        "1 2 3",
        "0",
        "1",
        "0.0 0.0",
        "1.5",
        "3",
    ]
)


class ReportBlockDeduplicationTests(SimpleTestCase):
    def test_new_report_blocks_ignores_existing_and_uploaded_duplicates(self):
        existing_block = ["1", "10.0", "8 12"]
        new_block = ["2", "12.0", "4 14"]

        blocks = new_report_blocks(
            current_blocks=[existing_block],
            uploaded_blocks=[existing_block, new_block, new_block],
        )

        self.assertEqual(blocks, [new_block])


class DatReportPayloadTests(SimpleTestCase):
    def test_uploaded_delta_can_declare_merged_level_count(self):
        level_count, blocks, error = dat_report_payload(
            f"3\n{VALID_LEVEL_BLOCK}\n",
            require_count_match=False,
        )

        self.assertIsNone(error)
        self.assertEqual(level_count, 3)
        self.assertEqual(len(blocks), 1)

    def test_existing_report_requires_header_to_match_blocks(self):
        level_count, blocks, error = dat_report_payload(
            f"3\n{VALID_LEVEL_BLOCK}\n",
            require_count_match=True,
        )

        self.assertEqual(error, "invalid")
        self.assertEqual(level_count, 0)
        self.assertEqual(blocks, [])


class StudyPlatformTests(SimpleTestCase):
    def test_only_android_platform_is_included_in_study_stats(self):
        self.assertTrue(is_study_client_platform("android"))
        self.assertTrue(is_study_client_platform(" Android "))
        self.assertFalse(is_study_client_platform("ios"))
        self.assertFalse(is_study_client_platform(""))


class FullReportStatsChartTests(SimpleTestCase):
    def test_global_stats_include_requested_chart_series(self):
        levels = [
            {
                "seed": 12,
                "time_spent": 10,
                "basket": [0, 0],
                "apple_tree": [4, 0],
                "visual": None,
                "trees": [],
                "player_positions": [[0, 0], [4, 0]],
                "final_distance": 0,
                "score": 3,
            },
            {
                "seed": 13,
                "time_spent": 10,
                "basket": [0, 0],
                "apple_tree": [2, 0],
                "visual": None,
                "trees": [],
                "player_positions": [[0, 0], [2, 0]],
                "final_distance": 0,
                "score": 1,
            },
        ]
        stats = full_report_stats(levels)

        for level in stats["levels"]:
            level["age"] = 70
            level["report"] = 4
            level["user"] = 9

        global_stats = full_reports_global_stats([{"stats": stats}])

        self.assertEqual(
            global_stats["charts"]["level_percent_by_age"],
            [
                {
                    "age": 70,
                    "level_count": 2,
                    "average_movement_percent": 37.5,
                }
            ],
        )
        self.assertEqual(
            global_stats["charts"]["score_by_age"],
            [
                {
                    "age": 70,
                    "level_count": 2,
                    "average_score": 2.0,
                }
            ],
        )
        self.assertEqual(
            global_stats["charts"]["stars_by_speed"],
            [
                {
                    "speed": 1.0,
                    "movement_percent": 50.0,
                    "stars": 3,
                    "age": 70,
                    "report": 4,
                    "user": 9,
                    "level": 1,
                    "seed": 12,
                },
                {
                    "speed": 0.5,
                    "movement_percent": 25.0,
                    "stars": 1,
                    "age": 70,
                    "report": 4,
                    "user": 9,
                    "level": 2,
                    "seed": 13,
                },
            ],
        )
