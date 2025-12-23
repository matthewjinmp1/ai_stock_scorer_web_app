#!/usr/bin/env python3
"""
Single-threaded and multithreaded computation benchmark.
Runs at max capacity for 5 seconds and prints the total number of computations.
"""

import time
import threading
import multiprocessing
from concurrent.futures import ThreadPoolExecutor


def compute():
    """Perform a minimal computation to maximize count."""
    # Simplest possible computation - just return a constant
    return 1


def single_thread_benchmark(duration=5.0):
    """Run single-threaded computation at max capacity for specified duration.
    
    Args:
        duration: Duration in seconds (default 5.0)
    """
    print("=" * 80)
    print("SINGLE-THREADED BENCHMARK")
    print("=" * 80)
    print(f"Starting single-threaded computation benchmark...")
    print(f"Running for {duration} seconds at max capacity...")
    
    start_time = time.time()
    end_time = start_time + duration
    computation_count = 0
    
    # Run computations as fast as possible until 5 seconds have passed
    # Check time less frequently to reduce overhead
    check_interval = 10000  # Check time every 10,000 computations
    while True:
        # Do a batch of computations before checking time
        for _ in range(check_interval):
            compute()
            computation_count += 1
        
        # Check time after batch
        if time.time() >= end_time:
            break
    
    elapsed_time = time.time() - start_time
    
    print(f"\nBenchmark complete!")
    print(f"Total computations: {computation_count:,}")
    print(f"Elapsed time: {elapsed_time:.4f} seconds")
    print(f"Computations per second: {computation_count / elapsed_time:,.0f}")
    return computation_count


def worker_thread(end_time, result_list, thread_id):
    """Worker thread that performs computations until end_time."""
    local_count = 0
    while time.time() < end_time:
        compute()
        local_count += 1
    result_list[thread_id] = local_count
    return local_count


def worker_process(end_time, result_queue, process_id):
    """Worker process that performs computations until end_time."""
    local_count = 0
    # Check time less frequently to reduce overhead
    check_interval = 10000  # Check time every 10,000 computations
    while True:
        # Do a batch of computations before checking time
        for _ in range(check_interval):
            # Simplest possible computation
            _ = 1
            local_count += 1
        
        # Check time after batch
        if time.time() >= end_time:
            break
    
    result_queue.put((process_id, local_count))
    return local_count


def multithread_benchmark(num_threads=None, duration=5.0):
    """Run multithreaded computation at max capacity for specified duration.
    
    Uses multiprocessing for true parallelism (bypasses Python's GIL).
    
    Args:
        num_threads: Number of processes to use. If None, uses CPU count.
        duration: Duration in seconds (default 5.0)
    """
    import os
    if num_threads is None:
        num_threads = os.cpu_count() or 4
    
    print("\n" + "=" * 80)
    print("MULTITHREADED BENCHMARK (using multiprocessing)")
    print("=" * 80)
    print(f"Starting multithreaded computation benchmark with {num_threads} processes...")
    print(f"Running for {duration} seconds at max capacity...")
    
    start_time = time.time()
    end_time = start_time + duration
    
    # Use multiprocessing for true parallelism (bypasses GIL)
    result_queue = multiprocessing.Queue()
    processes = []
    
    # Create and start processes
    for i in range(num_threads):
        process = multiprocessing.Process(target=worker_process, args=(end_time, result_queue, i))
        process.start()
        processes.append(process)
    
    # Wait for all processes to complete
    for process in processes:
        process.join()
    
    # Collect results
    results = {}
    while not result_queue.empty():
        process_id, count = result_queue.get()
        results[process_id] = count
    
    elapsed_time = time.time() - start_time
    total_computations = sum(results.values())
    
    print(f"\nBenchmark complete!")
    print(f"Number of processes: {num_threads}")
    print(f"Total computations: {total_computations:,}")
    print(f"Elapsed time: {elapsed_time:.4f} seconds")
    print(f"Computations per second: {total_computations / elapsed_time:,.0f}")
    print(f"Computations per process: {total_computations / num_threads:,.0f}")
    return total_computations


def main():
    """Run single-threaded or multithreaded benchmark based on user choice."""
    print("=" * 80)
    print("COMPUTATION BENCHMARK")
    print("=" * 80)
    print("\nChoose benchmark type:")
    print("  1 - Single-threaded")
    print("  2 - Multithreaded")
    print("\nYou can specify duration: '1 60' for single-threaded 60 seconds")
    print("                        or '2 60' for multithreaded 60 seconds")
    print("                        (default is 5 seconds)")
    
    while True:
        user_input = input("\nEnter choice (1 or 2, optionally followed by duration): ").strip()
        parts = user_input.split()
        
        if not parts:
            print("Invalid input. Please enter 1 or 2, optionally followed by duration.")
            continue
        
        choice = parts[0]
        duration = 5.0  # Default duration
        
        # Parse duration if provided
        if len(parts) > 1:
            try:
                duration = float(parts[1])
                if duration <= 0:
                    print("Duration must be positive. Using default 5 seconds.")
                    duration = 5.0
            except ValueError:
                print(f"Invalid duration '{parts[1]}'. Using default 5 seconds.")
        
        if choice == "1":
            single_thread_benchmark(duration)
            break
        elif choice == "2":
            multithread_benchmark(duration=duration)
            break
        else:
            print("Invalid choice. Please enter 1 or 2, optionally followed by duration.")


if __name__ == "__main__":
    # Required for Windows multiprocessing
    multiprocessing.freeze_support()
    main()
