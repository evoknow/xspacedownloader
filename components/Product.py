#!/usr/bin/env python3
"""Product management component for XSpace Downloader."""

import json
import logging
from datetime import datetime
from components.DatabaseManager import DatabaseManager

logger = logging.getLogger('webapp')

class Product:
    """Handles product management operations."""
    
    def __init__(self):
        """Initialize Product component."""
        self.db_manager = DatabaseManager()
        
    def get_all_products(self):
        """Get all products from database."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, sku, name, price, description, image_url, status, 
                       credits, recurring_credits, created_at, updated_at
                FROM products 
                ORDER BY created_at DESC
            """)
            
            products = cursor.fetchall()
            
            # Convert decimal and datetime objects for JSON serialization
            for product in products:
                if product['price']:
                    product['price'] = float(product['price'])
                if product['created_at']:
                    product['created_at'] = product['created_at'].isoformat()
                if product['updated_at']:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            cursor.close()
            connection.close()
            
            return products
            
        except Exception as e:
            logger.error(f"Error getting all products: {e}")
            return []
    
    def get_product_by_id(self, product_id):
        """Get a single product by ID."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, sku, name, price, description, image_url, status, 
                       credits, recurring_credits, created_at, updated_at
                FROM products 
                WHERE id = %s
            """, (product_id,))
            
            product = cursor.fetchone()
            
            if product:
                # Convert decimal and datetime objects for JSON serialization
                if product['price']:
                    product['price'] = float(product['price'])
                if product['created_at']:
                    product['created_at'] = product['created_at'].isoformat()
                if product['updated_at']:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            cursor.close()
            connection.close()
            
            return product
            
        except Exception as e:
            logger.error(f"Error getting product {product_id}: {e}")
            return None
    
    def get_product_by_sku(self, sku):
        """Get a single product by SKU."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, sku, name, price, description, image_url, status, 
                       credits, recurring_credits, created_at, updated_at
                FROM products 
                WHERE sku = %s
            """, (sku,))
            
            product = cursor.fetchone()
            
            if product:
                # Convert decimal and datetime objects for JSON serialization
                if product['price']:
                    product['price'] = float(product['price'])
                if product['created_at']:
                    product['created_at'] = product['created_at'].isoformat()
                if product['updated_at']:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            cursor.close()
            connection.close()
            
            return product
            
        except Exception as e:
            logger.error(f"Error getting product by SKU {sku}: {e}")
            return None
    
    def get_active_products(self):
        """Get only active products."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor(dictionary=True)
            
            cursor.execute("""
                SELECT id, sku, name, price, description, image_url, status, 
                       credits, recurring_credits, created_at, updated_at
                FROM products 
                WHERE status = 'active'
                ORDER BY price ASC
            """)
            
            products = cursor.fetchall()
            
            # Convert decimal and datetime objects for JSON serialization
            for product in products:
                if product['price']:
                    product['price'] = float(product['price'])
                if product['created_at']:
                    product['created_at'] = product['created_at'].isoformat()
                if product['updated_at']:
                    product['updated_at'] = product['updated_at'].isoformat()
            
            cursor.close()
            connection.close()
            
            return products
            
        except Exception as e:
            logger.error(f"Error getting active products: {e}")
            return []
    
    def create_product(self, product_data):
        """Create a new product."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Check if SKU already exists
            cursor.execute("SELECT id FROM products WHERE sku = %s", (product_data['sku'],))
            if cursor.fetchone():
                cursor.close()
                connection.close()
                return {'error': 'Product with this SKU already exists'}
            
            # Generate product ID (you may want to use a different ID generation method)
            import secrets
            product_id = f"prod_{secrets.token_urlsafe(16)}"
            
            cursor.execute("""
                INSERT INTO products 
                (id, sku, name, price, description, image_url, status, credits, recurring_credits)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                product_id,
                product_data['sku'],
                product_data['name'],
                float(product_data['price']),
                product_data.get('description'),
                product_data.get('image_url'),
                product_data.get('status', 'active'),
                int(product_data['credits']),
                product_data.get('recurring_credits', 'no')
            ))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Created product: {product_data['sku']} - {product_data['name']}")
            return {'success': True, 'product_id': product_id}
            
        except Exception as e:
            logger.error(f"Error creating product: {e}")
            return {'error': str(e)}
    
    def update_product(self, product_id, product_data):
        """Update an existing product."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Check if product exists
            cursor.execute("SELECT id FROM products WHERE id = %s", (product_id,))
            if not cursor.fetchone():
                cursor.close()
                connection.close()
                return {'error': 'Product not found'}
            
            # Check if SKU is being changed and if it conflicts with another product
            cursor.execute("SELECT id FROM products WHERE sku = %s AND id != %s", 
                          (product_data['sku'], product_id))
            if cursor.fetchone():
                cursor.close()
                connection.close()
                return {'error': 'Another product with this SKU already exists'}
            
            cursor.execute("""
                UPDATE products SET
                    sku = %s,
                    name = %s,
                    price = %s,
                    description = %s,
                    image_url = %s,
                    status = %s,
                    credits = %s,
                    recurring_credits = %s
                WHERE id = %s
            """, (
                product_data['sku'],
                product_data['name'],
                float(product_data['price']),
                product_data.get('description'),
                product_data.get('image_url'),
                product_data.get('status', 'active'),
                int(product_data['credits']),
                product_data.get('recurring_credits', 'no'),
                product_id
            ))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Updated product: {product_id}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error updating product {product_id}: {e}")
            return {'error': str(e)}
    
    def delete_product(self, product_id):
        """Delete a product."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Check if product exists
            cursor.execute("SELECT sku, name FROM products WHERE id = %s", (product_id,))
            product = cursor.fetchone()
            if not product:
                cursor.close()
                connection.close()
                return {'error': 'Product not found'}
            
            # Delete the product
            cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Deleted product: {product[0]} - {product[1]}")
            return {'success': True}
            
        except Exception as e:
            logger.error(f"Error deleting product {product_id}: {e}")
            return {'error': str(e)}
    
    def toggle_product_status(self, product_id):
        """Toggle product status between active and inactive."""
        try:
            connection = self.db_manager.get_connection()
            cursor = connection.cursor()
            
            # Get current status
            cursor.execute("SELECT status FROM products WHERE id = %s", (product_id,))
            result = cursor.fetchone()
            if not result:
                cursor.close()
                connection.close()
                return {'error': 'Product not found'}
            
            current_status = result[0]
            new_status = 'inactive' if current_status == 'active' else 'active'
            
            # Update status
            cursor.execute("UPDATE products SET status = %s WHERE id = %s", 
                          (new_status, product_id))
            
            connection.commit()
            cursor.close()
            connection.close()
            
            logger.info(f"Toggled product {product_id} status: {current_status} -> {new_status}")
            return {'success': True, 'new_status': new_status}
            
        except Exception as e:
            logger.error(f"Error toggling product status {product_id}: {e}")
            return {'error': str(e)}