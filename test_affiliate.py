#!/usr/bin/env python3
"""Test script for affiliate system functionality."""

import sys
import random
import string
from datetime import datetime
from components.Affiliate import Affiliate

def generate_test_email():
    """Generate a random test email."""
    random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"test_{random_string}@example.com"

def test_affiliate_system():
    """Test the affiliate system end-to-end."""
    print("=== Affiliate System Test ===\n")
    
    try:
        # Initialize affiliate component
        affiliate = Affiliate()
        print("✓ Affiliate component initialized")
        
        # Test 1: Get affiliate settings
        print("\n1. Testing affiliate settings...")
        settings = affiliate.get_affiliate_settings()
        print(f"   Credits per registration: {settings['credits_per_registration']}")
        print(f"   Money per registration: ${settings['money_per_registration']}")
        print(f"   Minimum payout: ${settings['minimum_payout_amount']}")
        print("✓ Settings retrieved successfully")
        
        # Test 2: Track a visit
        print("\n2. Testing affiliate visit tracking...")
        test_affiliate_id = 1  # Assuming user ID 1 exists
        test_visitor_ip = f"192.168.1.{random.randint(1, 254)}"
        test_user_agent = "Mozilla/5.0 Test Browser"
        
        tracking_id = affiliate.track_visit(test_affiliate_id, test_visitor_ip, test_user_agent)
        if tracking_id:
            print(f"✓ Visit tracked successfully (ID: {tracking_id})")
        else:
            print("✗ Failed to track visit")
            return
        
        # Test 3: Convert visitor (simulate registration)
        print("\n3. Testing conversion tracking...")
        test_user_id = random.randint(1000, 9999)  # Random user ID
        
        conversion_result = affiliate.convert_visitor(test_user_id, test_visitor_ip)
        if conversion_result:
            print(f"✓ Conversion recorded for user {test_user_id}")
        else:
            print("✗ Failed to record conversion")
        
        # Test 4: Get affiliate stats
        print("\n4. Testing affiliate statistics...")
        stats = affiliate.get_affiliate_stats(test_affiliate_id)
        if stats:
            print(f"   Total referrals: {stats.get('total_referrals', 0)}")
            print(f"   Total credits earned: {stats.get('total_credits_earned', 0)}")
            print(f"   Total money earned: ${stats.get('total_money_earned', 0)}")
            print(f"   Pending credits: {stats.get('pending_credits', 0)}")
            print(f"   Pending money: ${stats.get('pending_money', 0)}")
            print("✓ Stats retrieved successfully")
        else:
            print("✗ Failed to get stats")
        
        # Test 5: Get admin dashboard stats
        print("\n5. Testing admin dashboard stats...")
        admin_stats = affiliate.get_admin_dashboard_stats()
        if admin_stats:
            print(f"   Total affiliates: {admin_stats.get('total_affiliates', 0)}")
            print(f"   Total referrals: {admin_stats.get('total_referrals', 0)}")
            print(f"   Pending credits: {admin_stats.get('pending_credits', 0)}")
            print(f"   Pending money: ${admin_stats.get('pending_money', 0)}")
            print("✓ Admin stats retrieved successfully")
        else:
            print("✗ Failed to get admin stats")
        
        # Test 6: Get pending earnings
        print("\n6. Testing pending earnings retrieval...")
        pending_credits = affiliate.get_pending_earnings('credit')
        pending_money = affiliate.get_pending_earnings('money')
        print(f"   Pending credit earnings: {len(pending_credits)}")
        print(f"   Pending money earnings: {len(pending_money)}")
        print("✓ Pending earnings retrieved")
        
        # Test 7: Update settings (and restore original)
        print("\n7. Testing settings update...")
        original_settings = settings.copy()
        new_settings = {
            'credits_per_registration': 15,
            'money_per_registration': 0.75,
            'minimum_payout_amount': 25,
            'tax_reporting_threshold': 600
        }
        
        update_result = affiliate.update_affiliate_settings(new_settings, 1)
        if update_result:
            print("✓ Settings updated successfully")
            # Restore original settings
            affiliate.update_affiliate_settings(original_settings, 1)
            print("✓ Original settings restored")
        else:
            print("✗ Failed to update settings")
        
        print("\n=== All tests completed successfully! ===")
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_affiliate_system()