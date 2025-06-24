#!/usr/bin/env python3

import sys
import argparse
from datetime import datetime
from components.Ad import Ad


def list_ads(include_inactive=False):
    ads = Ad.get_all_ads(include_inactive=include_inactive)
    
    if not ads:
        print("No advertisements found.")
        return
    
    print(f"\n{'ID':<5} {'Status':<10} {'Start Date':<20} {'End Date':<20} {'Impressions':<15} {'Copy Preview':<50}")
    print("-" * 120)
    
    status_map = {
        0: "Pending",
        1: "Active",
        -1: "Deleted",
        -9: "Suspended"
    }
    
    for ad in ads:
        status = status_map.get(ad['status'], 'Unknown')
        copy_preview = ad['copy'][:47] + "..." if len(ad['copy']) > 50 else ad['copy']
        copy_preview = copy_preview.replace('\n', ' ').replace('\r', '')
        
        impressions = f"{ad['impression_count']}"
        if ad['max_impressions'] > 0:
            impressions += f"/{ad['max_impressions']}"
        
        print(f"{ad['id']:<5} {status:<10} {str(ad['start_date']):<20} {str(ad['end_date']):<20} {impressions:<15} {copy_preview:<50}")


def create_ad(copy, start_date, end_date, max_impressions=0):
    ad = Ad()
    ad.copy = copy
    ad.start_date = datetime.strptime(start_date, "%Y-%m-%d %H:%M:%S")
    ad.end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
    ad.status = 0  # Pending by default
    ad.max_impressions = max_impressions
    
    ad.save()
    print(f"Advertisement created successfully with ID: {ad.ad_id}")


def update_ad(ad_id, **kwargs):
    ad = Ad(ad_id)
    
    if not ad.copy:
        print(f"Advertisement with ID {ad_id} not found.")
        return
    
    if 'copy' in kwargs:
        ad.copy = kwargs['copy']
    if 'start_date' in kwargs:
        ad.start_date = datetime.strptime(kwargs['start_date'], "%Y-%m-%d %H:%M:%S")
    if 'end_date' in kwargs:
        ad.end_date = datetime.strptime(kwargs['end_date'], "%Y-%m-%d %H:%M:%S")
    if 'max_impressions' in kwargs:
        ad.max_impressions = kwargs['max_impressions']
    
    ad.save()
    print(f"Advertisement {ad_id} updated successfully.")


def change_status(ad_id, action):
    ad = Ad(ad_id)
    
    if not ad.copy:
        print(f"Advertisement with ID {ad_id} not found.")
        return
    
    if action == 'activate':
        ad.activate()
        print(f"Advertisement {ad_id} activated.")
    elif action == 'suspend':
        ad.suspend()
        print(f"Advertisement {ad_id} suspended.")
    elif action == 'delete':
        ad.delete()
        print(f"Advertisement {ad_id} deleted.")
    else:
        print(f"Unknown action: {action}")


def show_ad(ad_id):
    ad = Ad(ad_id)
    
    if not ad.copy:
        print(f"Advertisement with ID {ad_id} not found.")
        return
    
    print(f"\n--- Advertisement Details ---")
    print(f"ID: {ad.ad_id}")
    print(f"Status: {ad.status}")
    print(f"Start Date: {ad.start_date}")
    print(f"End Date: {ad.end_date}")
    print(f"Impressions: {ad.impression_count}/{ad.max_impressions if ad.max_impressions > 0 else 'unlimited'}")
    print(f"Created: {ad.created_at}")
    print(f"Updated: {ad.updated_at}")
    print(f"\nCopy:\n{ad.copy}")


def main():
    parser = argparse.ArgumentParser(description='Advertisement Management Tool')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List all advertisements')
    list_parser.add_argument('--all', action='store_true', help='Include deleted and suspended ads')
    
    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new advertisement')
    create_parser.add_argument('--copy', required=True, help='Advertisement copy (HTML allowed)')
    create_parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD HH:MM:SS)')
    create_parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD HH:MM:SS)')
    create_parser.add_argument('--max-impressions', type=int, default=0, help='Maximum impressions (0 for unlimited)')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update an advertisement')
    update_parser.add_argument('id', type=int, help='Advertisement ID')
    update_parser.add_argument('--copy', help='New advertisement copy')
    update_parser.add_argument('--start', help='New start date (YYYY-MM-DD HH:MM:SS)')
    update_parser.add_argument('--end', help='New end date (YYYY-MM-DD HH:MM:SS)')
    update_parser.add_argument('--max-impressions', type=int, help='New maximum impressions')
    
    # Status commands
    activate_parser = subparsers.add_parser('activate', help='Activate an advertisement')
    activate_parser.add_argument('id', type=int, help='Advertisement ID')
    
    suspend_parser = subparsers.add_parser('suspend', help='Suspend an advertisement')
    suspend_parser.add_argument('id', type=int, help='Advertisement ID')
    
    delete_parser = subparsers.add_parser('delete', help='Delete an advertisement')
    delete_parser.add_argument('id', type=int, help='Advertisement ID')
    
    # Show command
    show_parser = subparsers.add_parser('show', help='Show advertisement details')
    show_parser.add_argument('id', type=int, help='Advertisement ID')
    
    args = parser.parse_args()
    
    if args.command == 'list':
        list_ads(include_inactive=args.all)
    elif args.command == 'create':
        create_ad(args.copy, args.start, args.end, args.max_impressions)
    elif args.command == 'update':
        update_kwargs = {}
        if args.copy:
            update_kwargs['copy'] = args.copy
        if args.start:
            update_kwargs['start_date'] = args.start
        if args.end:
            update_kwargs['end_date'] = args.end
        if args.max_impressions is not None:
            update_kwargs['max_impressions'] = args.max_impressions
        update_ad(args.id, **update_kwargs)
    elif args.command == 'activate':
        change_status(args.id, 'activate')
    elif args.command == 'suspend':
        change_status(args.id, 'suspend')
    elif args.command == 'delete':
        change_status(args.id, 'delete')
    elif args.command == 'show':
        show_ad(args.id)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()