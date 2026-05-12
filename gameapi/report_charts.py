from io import BytesIO
import math


class ReportChartError(ValueError):
    pass


class ReportChartDependencyError(ReportChartError):
    pass


def _chart_libraries():
    try:
        import matplotlib

        matplotlib.use("Agg")

        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise ReportChartDependencyError(
            "matplotlib and numpy must be installed to generate report charts."
        ) from exc

    return plt, np


def _read_required_line(file_handle, field_name):
    line = file_handle.readline()
    if line == "":
        raise ReportChartError(f"Missing value for {field_name}.")
    return line.strip()


def _read_optional_line(file_handle):
    line = file_handle.readline()
    if line == "":
        return None
    return line.strip()


def _read_int(file_handle, field_name):
    try:
        return int(_read_required_line(file_handle, field_name))
    except ValueError as exc:
        raise ReportChartError(f"Invalid integer for {field_name}.") from exc


def _read_float(file_handle, field_name):
    try:
        return float(_read_required_line(file_handle, field_name))
    except ValueError as exc:
        raise ReportChartError(f"Invalid number for {field_name}.") from exc


def _read_int_pair(file_handle, field_name):
    values = _read_required_line(file_handle, field_name).split()
    if len(values) != 2:
        raise ReportChartError(f"Expected two integers for {field_name}.")

    try:
        return [int(value) for value in values]
    except ValueError as exc:
        raise ReportChartError(f"Invalid coordinates for {field_name}.") from exc


def _read_float_pair(file_handle, field_name):
    values = _read_required_line(file_handle, field_name).split()
    if len(values) != 2:
        raise ReportChartError(f"Expected two numbers for {field_name}.")

    try:
        return [float(value) for value in values]
    except ValueError as exc:
        raise ReportChartError(f"Invalid coordinates for {field_name}.") from exc


def _read_visual_marker(file_handle):
    values = _read_required_line(file_handle, "visual marker").split()
    if len(values) != 3:
        raise ReportChartError("Expected three integers for visual marker.")

    try:
        marker = [int(value) for value in values]
    except ValueError as exc:
        raise ReportChartError("Invalid visual marker.") from exc

    if marker[0] == 1:
        return marker[1:]
    return None


def _read_level(file_handle, level_number):
    seed = _read_int(file_handle, f"level {level_number} seed")
    time_spent = _read_float(file_handle, f"level {level_number} time")
    basket = _read_int_pair(file_handle, f"level {level_number} basket")
    apple_tree = _read_int_pair(file_handle, f"level {level_number} apple tree")
    visual = _read_visual_marker(file_handle)

    tree_count = _read_int(file_handle, f"level {level_number} tree count")
    trees = [
        _read_int_pair(file_handle, f"level {level_number} tree {index + 1}")
        for index in range(tree_count)
    ]

    position_count = _read_int(file_handle, f"level {level_number} position count")
    player_positions = [
        _read_float_pair(file_handle, f"level {level_number} position {index + 1}")
        for index in range(position_count)
    ]

    final_distance = None
    score = None

    final_distance_line = _read_optional_line(file_handle)
    if final_distance_line is not None:
        try:
            final_distance = float(final_distance_line)
        except ValueError as exc:
            raise ReportChartError(
                f"Invalid number for level {level_number} final distance."
            ) from exc

        try:
            score = int(_read_required_line(file_handle, f"level {level_number} score"))
        except ValueError as exc:
            raise ReportChartError(f"Invalid integer for level {level_number} score.") from exc

    return {
        "seed": seed,
        "time_spent": time_spent,
        "basket": basket,
        "apple_tree": apple_tree,
        "visual": visual,
        "trees": trees,
        "player_positions": player_positions,
        "final_distance": final_distance,
        "score": score,
    }


def _parse_report(file_handle):
    level_count = _read_int(file_handle, "level count")
    if level_count < 1:
        raise ReportChartError("The report must contain at least one level.")

    return [
        _read_level(file_handle, level_number)
        for level_number in range(1, level_count + 1)
    ]


def parse_full_report(file_handle):
    return _parse_report(file_handle)


def distance_between(first_point, second_point):
    return math.sqrt(
        (second_point[0] - first_point[0]) ** 2
        + (second_point[1] - first_point[1]) ** 2
    )


def path_distance(points):
    if len(points) < 2:
        return 0

    return sum(
        distance_between(points[index], points[index + 1])
        for index in range(len(points) - 1)
    )


def level_stats(level, level_index):
    player_positions = level["player_positions"]
    traveled_distance = path_distance(player_positions)
    target_distance = distance_between(level["basket"], level["apple_tree"])
    tree_count = len(level["trees"])
    malus_time = 6 + 2 * tree_count
    playable_time = max(level["time_spent"] - malus_time, 0)
    expected_distance = playable_time * 2
    speed = traveled_distance / playable_time if playable_time else 0
    movement_ratio = (
        traveled_distance / expected_distance
        if expected_distance
        else 0
    )

    return {
        "level": level_index + 1,
        "seed": level["seed"],
        "time_spent": level["time_spent"],
        "playable_time": playable_time,
        "malus_time": malus_time,
        "basket": level["basket"],
        "apple_tree": level["apple_tree"],
        "visual": level["visual"],
        "has_visual": level["visual"] is not None,
        "tree_count": tree_count,
        "position_count": len(player_positions),
        "start_position": player_positions[0] if player_positions else None,
        "end_position": player_positions[-1] if player_positions else None,
        "traveled_distance": traveled_distance,
        "target_distance": target_distance,
        "expected_distance": expected_distance,
        "speed": speed,
        "movement_ratio": movement_ratio,
        "movement_percent": movement_ratio * 100,
        "final_distance": level["final_distance"],
        "score": level["score"],
        "is_interrupted": level["final_distance"] is None or level["score"] is None,
    }


def average(values):
    return sum(values) / len(values) if values else None


def full_report_stats(levels):
    per_level = [
        level_stats(level, level_index)
        for level_index, level in enumerate(levels)
    ]
    completed_levels = [
        level for level in per_level
        if not level["is_interrupted"]
    ]

    return {
        "level_count": len(per_level),
        "completed_level_count": len(completed_levels),
        "interrupted_level_count": len(per_level) - len(completed_levels),
        "total_time_spent": sum(level["time_spent"] for level in per_level),
        "total_playable_time": sum(level["playable_time"] for level in per_level),
        "total_traveled_distance": sum(
            level["traveled_distance"]
            for level in per_level
        ),
        "average_time_spent": average(
            [level["time_spent"] for level in per_level]
        ),
        "average_playable_time": average(
            [level["playable_time"] for level in per_level]
        ),
        "average_traveled_distance": average(
            [level["traveled_distance"] for level in per_level]
        ),
        "average_final_distance": average(
            [
                level["final_distance"]
                for level in completed_levels
                if level["final_distance"] is not None
            ]
        ),
        "average_score": average(
            [
                level["score"]
                for level in completed_levels
                if level["score"] is not None
            ]
        ),
        "average_movement_percent": average(
            [level["movement_percent"] for level in per_level]
        ),
        "average_speed": average(
            [level["speed"] for level in per_level]
        ),
        "seeds": [level["seed"] for level in per_level],
        "levels": per_level,
    }


def grouped_level_stats(levels, key):
    groups = {}
    for level in levels:
        group_key = level[key]
        if group_key is None:
            group_key = "unknown"

        groups.setdefault(str(group_key), []).append(level)

    return {
        group_key: summarize_levels(group_levels)
        for group_key, group_levels in groups.items()
    }


def level_percent_by_age_chart(levels):
    groups = {}
    for level in levels:
        groups.setdefault(level.get("age"), []).append(level)

    rows = []
    for age, age_levels in groups.items():
        rows.append(
            {
                "age": age,
                "level_count": len(age_levels),
                "average_movement_percent": average(
                    [level["movement_percent"] for level in age_levels]
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            row["age"] is None,
            row["age"] if row["age"] is not None else 0,
        ),
    )


def score_by_age_chart(levels):
    groups = {}
    for level in levels:
        if level["is_interrupted"] or level["score"] is None:
            continue

        groups.setdefault(level.get("age"), []).append(level)

    rows = []
    for age, age_levels in groups.items():
        rows.append(
            {
                "age": age,
                "level_count": len(age_levels),
                "average_score": average([level["score"] for level in age_levels]),
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            row["age"] is None,
            row["age"] if row["age"] is not None else 0,
        ),
    )


def stars_by_speed_chart(levels):
    return [
        {
            "speed": level["speed"],
            "movement_percent": level["movement_percent"],
            "stars": level["score"],
            "age": level.get("age"),
            "report": level.get("report"),
            "user": level.get("user"),
            "level": level["level"],
            "seed": level["seed"],
        }
        for level in levels
        if not level["is_interrupted"] and level["score"] is not None
    ]


def full_reports_charts(levels):
    return {
        "level_percent_by_age": level_percent_by_age_chart(levels),
        "score_by_age": score_by_age_chart(levels),
        "stars_by_speed": stars_by_speed_chart(levels),
    }


def summarize_levels(levels):
    completed_levels = [
        level for level in levels
        if not level["is_interrupted"]
    ]

    return {
        "level_count": len(levels),
        "completed_level_count": len(completed_levels),
        "interrupted_level_count": len(levels) - len(completed_levels),
        "total_time_spent": sum(level["time_spent"] for level in levels),
        "total_playable_time": sum(level["playable_time"] for level in levels),
        "total_traveled_distance": sum(
            level["traveled_distance"]
            for level in levels
        ),
        "average_time_spent": average(
            [level["time_spent"] for level in levels]
        ),
        "average_playable_time": average(
            [level["playable_time"] for level in levels]
        ),
        "average_traveled_distance": average(
            [level["traveled_distance"] for level in levels]
        ),
        "average_final_distance": average(
            [
                level["final_distance"]
                for level in completed_levels
                if level["final_distance"] is not None
            ]
        ),
        "average_score": average(
            [
                level["score"]
                for level in completed_levels
                if level["score"] is not None
            ]
        ),
        "average_movement_percent": average(
            [level["movement_percent"] for level in levels]
        ),
        "average_speed": average(
            [level["speed"] for level in levels]
        ),
    }


def full_reports_global_stats(report_stats):
    levels = []
    for report in report_stats:
        levels.extend(report["stats"]["levels"])

    summary = summarize_levels(levels)
    summary["by_seed"] = grouped_level_stats(levels, "seed")
    summary["charts"] = full_reports_charts(levels)
    return summary


def _plot_level(ax, level, level_index, plt, np):
    basket = level["basket"]
    apple_tree = level["apple_tree"]
    visual = level["visual"]
    trees = level["trees"]
    player_positions = level["player_positions"]

    ax.plot(basket[0], basket[1], "bo", markersize=8)
    ax.plot(apple_tree[0], apple_tree[1], "ro", markersize=8)

    if visual:
        ax.plot(visual[0], visual[1], "go", markersize=8)

    for tree in trees:
        ax.plot(tree[0], tree[1], "bs", markersize=6)

    if player_positions:
        ax.plot(
            player_positions[0][0],
            player_positions[0][1],
            "mo",
            markersize=10,
            markeredgewidth=2,
            markeredgecolor="black",
        )

    distance = 0
    if len(player_positions) > 1:
        colors = plt.cm.jet(np.linspace(0, 1, len(player_positions) - 1))
        for index in range(len(player_positions) - 1):
            x_values = [player_positions[index][0], player_positions[index + 1][0]]
            y_values = [player_positions[index][1], player_positions[index + 1][1]]
            ax.plot(x_values, y_values, color=colors[index], linewidth=2)
            distance += math.sqrt(
                (x_values[1] - x_values[0]) ** 2
                + (y_values[1] - y_values[0]) ** 2
            )

    target_distance = math.sqrt(
        (basket[0] - apple_tree[0]) ** 2 + (basket[1] - apple_tree[1]) ** 2
    )
    radius_20 = target_distance * math.sin(20 * math.pi / 180)
    radius_40 = target_distance * math.sin(40 * math.pi / 180)

    ax.add_patch(
        plt.Circle((basket[0], basket[1]), radius_20, fill=False, color="cyan", linestyle="--")
    )
    ax.add_patch(
        plt.Circle((basket[0], basket[1]), radius_40, fill=False, color="magenta", linestyle="--")
    )

    malus = 6 + 2 * len(trees)
    playable_time = max(level["time_spent"] - malus, 0)
    percentage = distance / (playable_time * 2) if playable_time else 0

    ax.set_title(f"Niveau {level_index + 1} - Pourcentage {int(percentage * 100)}%")
    ax.grid(True, alpha=0.3)
    ax.set_aspect("equal")
    ax.set_xlim(-2, 18)
    ax.set_ylim(-2, 18)


def _legend_handles(plt, np):
    colors_gradient = plt.cm.jet(np.linspace(0, 1, 10))
    return [
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="b", markersize=8, label="Panier"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="r", markersize=8, label="Pommier"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor="g", markersize=8, label="Repere Visuel"),
        plt.Line2D([0], [0], marker="s", color="w", markerfacecolor="b", markersize=6, label="Arbre(s)"),
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="m",
            markersize=10,
            markeredgecolor="black",
            markeredgewidth=2,
            label="Depart du joueur",
        ),
        plt.Line2D([0], [0], color=colors_gradient[0], linewidth=3, label="Position joueur"),
        plt.Line2D([0], [0], color="cyan", linewidth=2, linestyle="--", label="Seuil 20 degres"),
        plt.Line2D([0], [0], color="magenta", linewidth=2, linestyle="--", label="Seuil 40 degres"),
    ]


def generate_full_report_chart(file_handle):
    plt, np = _chart_libraries()
    levels = _parse_report(file_handle)

    columns = min(5, len(levels))
    rows = math.ceil(len(levels) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(4 * columns, 4 * rows))
    axes = np.array(axes).flatten()

    for index, level in enumerate(levels):
        _plot_level(axes[index], level, index, plt, np)

    for index in range(len(levels), len(axes)):
        axes[index].axis("off")

    fig.legend(
        handles=_legend_handles(plt, np),
        loc="upper center",
        bbox_to_anchor=(0.5, 0.98),
        ncol=4,
        fontsize=10,
    )
    plt.tight_layout(rect=[0, 0, 1, 0.94], pad=4, w_pad=5.0, h_pad=5.0)

    output = BytesIO()
    fig.savefig(output, format="png", bbox_inches="tight")
    plt.close(fig)
    output.seek(0)
    return output
