#!/usr/bin/env python3
"""Test script for space reviews functionality."""

import sys
import json
from components.Space import Space

def test_reviews():
    """Test all review functionality."""
    print("=== Testing Space Reviews ===\n")
    
    # Initialize Space component
    try:
        space = Space()
        print("✅ Space component initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize Space component: {e}")
        return
    
    # Test space ID (you can change this to test with a different space)
    test_space_id = "1lDxLnrWjwkGm"
    
    # Test user data
    test_user_id = 1  # Change to 0 for anonymous user
    test_cookie_id = "test_cookie_123"
    
    print(f"\nTesting with space_id: {test_space_id}")
    print(f"User ID: {test_user_id}, Cookie ID: {test_cookie_id}")
    
    # 1. Test adding a review
    print("\n1. Testing add_review...")
    result = space.add_review(
        space_id=test_space_id,
        user_id=test_user_id,
        cookie_id=test_cookie_id,
        rating=5,
        review_text="This is a great space! Very informative discussion."
    )
    
    if result['success']:
        review_id = result['review_id']
        print(f"✅ Review added successfully! Review ID: {review_id}")
    else:
        print(f"❌ Failed to add review: {result.get('error', 'Unknown error')}")
        review_id = None
    
    # 2. Test getting reviews
    print("\n2. Testing get_reviews...")
    result = space.get_reviews(test_space_id)
    
    if result['success']:
        print(f"✅ Retrieved reviews successfully!")
        print(f"   Average rating: {result['average_rating']}")
        print(f"   Total reviews: {result['total_reviews']}")
        if result['reviews']:
            print("   Reviews:")
            for review in result['reviews']:
                print(f"   - {review['author']}: {review['rating']}⭐ - {review.get('review', 'No text')}")
    else:
        print(f"❌ Failed to get reviews: {result.get('error', 'Unknown error')}")
    
    # 3. Test updating a review (if we successfully added one)
    if review_id:
        print("\n3. Testing update_review...")
        result = space.update_review(
            review_id=review_id,
            user_id=test_user_id,
            cookie_id=test_cookie_id,
            rating=4,
            review_text="Updated review: Still a good space, but could be better organized."
        )
        
        if result['success']:
            print(f"✅ Review updated successfully!")
        else:
            print(f"❌ Failed to update review: {result.get('error', 'Unknown error')}")
    
    # 4. Test adding duplicate review (should fail)
    print("\n4. Testing duplicate review (should fail)...")
    result = space.add_review(
        space_id=test_space_id,
        user_id=test_user_id,
        cookie_id=test_cookie_id,
        rating=3,
        review_text="Trying to add another review"
    )
    
    if not result['success'] and "already reviewed" in result.get('error', ''):
        print(f"✅ Correctly prevented duplicate review: {result['error']}")
    else:
        print(f"❌ Duplicate review check failed!")
    
    # 5. Test invalid rating
    print("\n5. Testing invalid rating...")
    result = space.add_review(
        space_id=test_space_id,
        user_id=2,  # Different user
        cookie_id="different_cookie",
        rating=10,  # Invalid rating
        review_text="Testing invalid rating"
    )
    
    if not result['success'] and "between 1 and 5" in result.get('error', ''):
        print(f"✅ Correctly rejected invalid rating: {result['error']}")
    else:
        print(f"❌ Invalid rating check failed!")
    
    # 6. Test deleting a review (if we have one)
    if review_id:
        print("\n6. Testing delete_review...")
        result = space.delete_review(
            review_id=review_id,
            user_id=test_user_id,
            cookie_id=test_cookie_id,
            space_id=test_space_id
        )
        
        if result['success']:
            print(f"✅ Review deleted successfully!")
        else:
            print(f"❌ Failed to delete review: {result.get('error', 'Unknown error')}")
    
    # 7. Test anonymous user review
    print("\n7. Testing anonymous user review...")
    result = space.add_review(
        space_id=test_space_id,
        user_id=0,  # Anonymous
        cookie_id="anon_cookie_456",
        rating=4,
        review_text="Anonymous review test"
    )
    
    if result['success']:
        anon_review_id = result['review_id']
        print(f"✅ Anonymous review added successfully! Review ID: {anon_review_id}")
        
        # Clean up
        space.delete_review(anon_review_id, 0, "anon_cookie_456")
    else:
        print(f"❌ Failed to add anonymous review: {result.get('error', 'Unknown error')}")
    
    print("\n=== Review Tests Complete ===")

if __name__ == "__main__":
    test_reviews()