#!/usr/bin/env python3
"""Benchmark script for chip data query performance.

This script measures the performance of different query strategies
for chip data retrieval, comparing:
1. Full ChipDocument retrieval (current approach)
2. Projection-based retrieval (summary only)
3. Individual QubitDocument retrieval
4. Aggregation Pipeline for metrics

Usage:
    # From project root with docker compose running:
    docker compose exec api python scripts/benchmark_chip_queries.py

    # Or directly if running locally:
    python scripts/benchmark_chip_queries.py --chip-id <chip_id> --project-id <project_id>
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    name: str
    duration_ms: float
    document_count: int
    data_size_kb: float
    notes: str = ""


def init_database() -> None:
    """Initialize database connection."""
    from qdash.api.db.session import init_db

    init_db()


def get_chip_ids(project_id: str | None = None) -> list[dict[str, Any]]:
    """Get available chip IDs."""
    from qdash.dbmodel.chip import ChipDocument

    query: dict[str, Any] = {}
    if project_id:
        query["project_id"] = project_id

    chips = ChipDocument.find(query).run()
    return [
        {
            "chip_id": c.chip_id,
            "project_id": c.project_id,
            "size": c.size,
            "qubit_count": len(c.qubits),
            "coupling_count": len(c.couplings),
        }
        for c in chips
    ]


def measure_time(func: Any) -> tuple[Any, float]:
    """Measure execution time of a function."""
    start = time.perf_counter()
    result = func()
    end = time.perf_counter()
    return result, (end - start) * 1000  # Convert to milliseconds


def get_data_size(obj: Any) -> float:
    """Get approximate size of object in KB."""
    if hasattr(obj, "model_dump_json"):
        return len(obj.model_dump_json()) / 1024
    if hasattr(obj, "model_dump"):
        return len(json.dumps(obj.model_dump(), default=str)) / 1024
    if isinstance(obj, list):
        return sum(get_data_size(item) for item in obj)
    if isinstance(obj, dict):
        return len(json.dumps(obj, default=str)) / 1024
    return 0


def benchmark_full_chip_document(project_id: str, chip_id: str) -> BenchmarkResult:
    """Benchmark: Retrieve full ChipDocument (current approach)."""
    from qdash.dbmodel.chip import ChipDocument

    def query() -> ChipDocument | None:
        return ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id}).run()

    result, duration = measure_time(query)

    return BenchmarkResult(
        name="Full ChipDocument",
        duration_ms=duration,
        document_count=1 if result else 0,
        data_size_kb=get_data_size(result) if result else 0,
        notes="Current approach - retrieves all embedded qubits/couplings",
    )


def benchmark_chip_projection(project_id: str, chip_id: str) -> BenchmarkResult:
    """Benchmark: Retrieve ChipDocument with projection (summary only)."""
    from qdash.dbmodel.chip import ChipDocument

    def query() -> dict[str, Any] | None:
        # Use raw MongoDB query with projection
        result = (
            ChipDocument.find_one({"project_id": project_id, "chip_id": chip_id})
            .project(
                {
                    "chip_id": 1,
                    "size": 1,
                    "topology_id": 1,
                    "installed_at": 1,
                    "system_info": 1,
                    # Exclude heavy fields
                    "qubits": 0,
                    "couplings": 0,
                }
            )
            .run()
        )
        return result

    result, duration = measure_time(query)

    return BenchmarkResult(
        name="ChipDocument with Projection",
        duration_ms=duration,
        document_count=1 if result else 0,
        data_size_kb=get_data_size(result) if result else 0,
        notes="Summary only - excludes qubits/couplings",
    )


def benchmark_qubit_documents(project_id: str, chip_id: str) -> BenchmarkResult:
    """Benchmark: Retrieve all QubitDocuments separately."""
    from qdash.dbmodel.qubit import QubitDocument

    def query() -> list[Any]:
        return list(QubitDocument.find({"project_id": project_id, "chip_id": chip_id}).run())

    result, duration = measure_time(query)

    return BenchmarkResult(
        name="All QubitDocuments",
        duration_ms=duration,
        document_count=len(result),
        data_size_kb=get_data_size(result),
        notes="Separate collection query",
    )


def benchmark_qubit_projection(project_id: str, chip_id: str) -> BenchmarkResult:
    """Benchmark: Retrieve QubitDocuments with projection (metrics only)."""
    from qdash.dbmodel.qubit import QubitDocument

    def query() -> list[Any]:
        return list(
            QubitDocument.find({"project_id": project_id, "chip_id": chip_id})
            .project(
                {
                    "qid": 1,
                    "data.t1.value": 1,
                    "data.t2_echo.value": 1,
                    "data.qubit_frequency.value": 1,
                    "data.average_readout_fidelity.value": 1,
                }
            )
            .run()
        )

    result, duration = measure_time(query)

    return BenchmarkResult(
        name="QubitDocuments with Projection",
        duration_ms=duration,
        document_count=len(result),
        data_size_kb=get_data_size(result),
        notes="Only key metrics fields",
    )


def benchmark_aggregation_metrics(project_id: str, chip_id: str) -> BenchmarkResult:
    """Benchmark: Use aggregation pipeline for metrics."""
    from qdash.dbmodel.qubit import QubitDocument

    def query() -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {
                "$project": {
                    "qid": 1,
                    "t1": "$data.t1.value",
                    "t2_echo": "$data.t2_echo.value",
                    "qubit_frequency": "$data.qubit_frequency.value",
                    "average_readout_fidelity": "$data.average_readout_fidelity.value",
                }
            },
        ]
        return list(QubitDocument.aggregate(pipeline).run())

    result, duration = measure_time(query)

    return BenchmarkResult(
        name="Aggregation Pipeline (metrics)",
        duration_ms=duration,
        document_count=len(result),
        data_size_kb=get_data_size(result),
        notes="DB-side projection and transformation",
    )


def benchmark_aggregation_summary(project_id: str, chip_id: str) -> BenchmarkResult:
    """Benchmark: Use aggregation pipeline for summary statistics."""
    from qdash.dbmodel.qubit import QubitDocument

    def query() -> list[dict[str, Any]]:
        pipeline = [
            {"$match": {"project_id": project_id, "chip_id": chip_id}},
            {
                "$group": {
                    "_id": None,
                    "avg_t1": {"$avg": "$data.t1.value"},
                    "avg_t2_echo": {"$avg": "$data.t2_echo.value"},
                    "avg_qubit_frequency": {"$avg": "$data.qubit_frequency.value"},
                    "avg_readout_fidelity": {"$avg": "$data.average_readout_fidelity.value"},
                    "qubit_count": {"$sum": 1},
                    "calibrated_count": {
                        "$sum": {"$cond": [{"$ifNull": ["$data.t1.value", False]}, 1, 0]}
                    },
                }
            },
        ]
        return list(QubitDocument.aggregate(pipeline).run())

    result, duration = measure_time(query)

    return BenchmarkResult(
        name="Aggregation Pipeline (summary)",
        duration_ms=duration,
        document_count=1 if result else 0,
        data_size_kb=get_data_size(result),
        notes="DB-side aggregation for dashboard",
    )


def benchmark_single_qubit(project_id: str, chip_id: str, qid: str = "0") -> BenchmarkResult:
    """Benchmark: Retrieve single qubit from ChipDocument vs QubitDocument."""
    from qdash.dbmodel.qubit import QubitDocument

    def query() -> Any:
        return QubitDocument.find_one(
            {"project_id": project_id, "chip_id": chip_id, "qid": qid}
        ).run()

    result, duration = measure_time(query)

    return BenchmarkResult(
        name=f"Single QubitDocument (qid={qid})",
        duration_ms=duration,
        document_count=1 if result else 0,
        data_size_kb=get_data_size(result) if result else 0,
        notes="Direct single document lookup",
    )


def run_benchmarks(project_id: str, chip_id: str, iterations: int = 5) -> list[BenchmarkResult]:
    """Run all benchmarks multiple times and return average results."""
    benchmarks = [
        ("full_chip", lambda: benchmark_full_chip_document(project_id, chip_id)),
        ("chip_projection", lambda: benchmark_chip_projection(project_id, chip_id)),
        ("qubit_documents", lambda: benchmark_qubit_documents(project_id, chip_id)),
        ("qubit_projection", lambda: benchmark_qubit_projection(project_id, chip_id)),
        ("aggregation_metrics", lambda: benchmark_aggregation_metrics(project_id, chip_id)),
        ("aggregation_summary", lambda: benchmark_aggregation_summary(project_id, chip_id)),
        ("single_qubit", lambda: benchmark_single_qubit(project_id, chip_id)),
    ]

    results: dict[str, list[BenchmarkResult]] = {name: [] for name, _ in benchmarks}

    # Warm-up run
    print("Warming up...")
    for _, bench_func in benchmarks:
        bench_func()

    # Actual benchmark runs
    print(f"Running {iterations} iterations...")
    for i in range(iterations):
        print(f"  Iteration {i + 1}/{iterations}")
        for name, bench_func in benchmarks:
            results[name].append(bench_func())

    # Calculate averages
    avg_results = []
    for name, _ in benchmarks:
        runs = results[name]
        avg_result = BenchmarkResult(
            name=runs[0].name,
            duration_ms=sum(r.duration_ms for r in runs) / len(runs),
            document_count=runs[0].document_count,
            data_size_kb=runs[0].data_size_kb,
            notes=runs[0].notes,
        )
        avg_results.append(avg_result)

    return avg_results


def print_results(results: list[BenchmarkResult], chip_info: dict[str, Any]) -> None:
    """Print benchmark results in a formatted table."""
    print("\n" + "=" * 80)
    print("BENCHMARK RESULTS")
    print("=" * 80)
    print(f"\nChip: {chip_info['chip_id']}")
    print(f"Size: {chip_info['size']} qubits")
    print(f"Qubit count: {chip_info['qubit_count']}")
    print(f"Coupling count: {chip_info['coupling_count']}")
    print("\n" + "-" * 80)
    print(f"{'Query Type':<35} {'Time (ms)':<12} {'Docs':<8} {'Size (KB)':<12} {'Notes'}")
    print("-" * 80)

    baseline = results[0].duration_ms  # Full ChipDocument as baseline

    for result in results:
        speedup = baseline / result.duration_ms if result.duration_ms > 0 else 0
        speedup_str = f"({speedup:.1f}x)" if speedup > 1.1 else ""
        print(
            f"{result.name:<35} {result.duration_ms:<12.2f} {result.document_count:<8} "
            f"{result.data_size_kb:<12.1f} {speedup_str}"
        )

    print("-" * 80)
    print("\nKey findings:")

    # Find best for each use case
    summary_result = next((r for r in results if "summary" in r.name.lower()), None)
    projection_result = next((r for r in results if "Projection" in r.name and "Chip" in r.name), None)
    single_result = next((r for r in results if "Single" in r.name), None)

    if projection_result and baseline > 0:
        print(
            f"  - Chip summary: {projection_result.data_size_kb:.1f}KB vs "
            f"{results[0].data_size_kb:.1f}KB ({results[0].data_size_kb / projection_result.data_size_kb:.0f}x smaller)"
        )

    if summary_result:
        print(f"  - Dashboard aggregation: {summary_result.duration_ms:.2f}ms, {summary_result.data_size_kb:.1f}KB")

    if single_result:
        print(
            f"  - Single qubit lookup: {single_result.duration_ms:.2f}ms vs "
            f"{results[0].duration_ms:.2f}ms full chip"
        )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Benchmark chip data query performance")
    parser.add_argument("--chip-id", help="Specific chip ID to benchmark")
    parser.add_argument("--project-id", help="Project ID to filter chips")
    parser.add_argument("--iterations", type=int, default=5, help="Number of benchmark iterations")
    parser.add_argument("--list", action="store_true", help="List available chips and exit")
    args = parser.parse_args()

    print("Initializing database connection...")
    init_database()

    # List available chips
    chips = get_chip_ids(args.project_id)

    if not chips:
        print("No chips found in database.")
        print("Please ensure MongoDB is running and contains chip data.")
        sys.exit(1)

    if args.list:
        print("\nAvailable chips:")
        print(f"{'Chip ID':<20} {'Project ID':<40} {'Size':<8} {'Qubits':<8} {'Couplings'}")
        print("-" * 90)
        for chip in chips:
            print(
                f"{chip['chip_id']:<20} {chip['project_id']:<40} "
                f"{chip['size']:<8} {chip['qubit_count']:<8} {chip['coupling_count']}"
            )
        sys.exit(0)

    # Select chip to benchmark
    if args.chip_id:
        chip_info = next((c for c in chips if c["chip_id"] == args.chip_id), None)
        if not chip_info:
            print(f"Chip '{args.chip_id}' not found.")
            sys.exit(1)
    else:
        # Use largest chip by default
        chip_info = max(chips, key=lambda c: c["qubit_count"])
        print(f"No chip specified, using largest: {chip_info['chip_id']} ({chip_info['qubit_count']} qubits)")

    # Run benchmarks
    print(f"\nBenchmarking chip: {chip_info['chip_id']}")
    results = run_benchmarks(
        project_id=chip_info["project_id"],
        chip_id=chip_info["chip_id"],
        iterations=args.iterations,
    )

    # Print results
    print_results(results, chip_info)


if __name__ == "__main__":
    main()
