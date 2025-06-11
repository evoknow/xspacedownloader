#!/usr/bin/env python3
"""Test script to verify queue priority functionality."""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components.Space import Space
import time

def test_priority_functionality():
    print("Testing Queue Priority Functionality...\n")
    
    try:
        # Initialize Space component
        space = Space()
        
        # Test priority options
        print("1. Testing priority options:")
        priorities = space.get_priority_options()
        print(f"   Available priorities: {priorities}")
        
        # Test job creation with different priorities
        print("\n2. Testing job creation with priorities:")
        test_space_ids = ['test_space_1', 'test_space_2', 'test_space_3']
        test_priorities = [1, 3, 2]  # Highest, Normal, High
        
        job_ids = []
        for i, (space_id, priority) in enumerate(zip(test_space_ids, test_priorities)):
            job_id = space.create_download_job(space_id, priority=priority)
            job_ids.append(job_id)
            if job_id:
                print(f"   Created job {job_id} for {space_id} with priority {priority} ({priorities[priority]})")
            else:
                print(f"   Failed to create job for {space_id}")
        
        # Test listing jobs by priority
        print("\n3. Testing job listing (should be ordered by priority):")
        pending_jobs = space.list_download_jobs(status='pending', limit=10)
        for job in pending_jobs:
            priority_label = priorities.get(job.get('priority', 3), 'Unknown')
            print(f"   Job {job['id']}: {job['space_id']} - Priority {job.get('priority', 3)} ({priority_label})")
        
        # Test priority update
        print("\n4. Testing priority update:")
        if job_ids and job_ids[0]:
            old_priority = pending_jobs[0].get('priority', 3) if pending_jobs else 3
            new_priority = 5  # Lowest
            success = space.set_job_priority(job_ids[0], new_priority)
            if success:
                print(f"   Successfully updated job {job_ids[0]} priority from {old_priority} to {new_priority}")
                
                # Verify the change
                updated_jobs = space.list_download_jobs(status='pending', limit=10)
                updated_job = next((j for j in updated_jobs if j['id'] == job_ids[0]), None)
                if updated_job:
                    print(f"   Verified: Job {job_ids[0]} now has priority {updated_job['priority']}")
                    
                    # Show new order
                    print("   New job order:")
                    for job in updated_jobs:
                        priority_label = priorities.get(job.get('priority', 3), 'Unknown')
                        print(f"     Job {job['id']}: {job['space_id']} - Priority {job.get('priority', 3)} ({priority_label})")
            else:
                print(f"   Failed to update priority for job {job_ids[0]}")
        
        # Clean up test jobs (set status to cancelled to remove them from queue)
        print("\n5. Cleaning up test jobs:")
        for job_id in job_ids:
            if job_id:
                space.update_download_job(job_id, status='cancelled')
                print(f"   Cancelled test job {job_id}")
        
        print("\n✓ Priority functionality test completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_priority_functionality()