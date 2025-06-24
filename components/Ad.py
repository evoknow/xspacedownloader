import mysql.connector
import json
from datetime import datetime
import random


class Ad:
    def __init__(self, ad_id=None):
        with open('db_config.json', 'r') as f:
            self.config = json.load(f)['mysql']
        
        self.ad_id = ad_id
        self.copy = None
        self.start_date = None
        self.end_date = None
        self.status = None
        self.impression_count = 0
        self.max_impressions = 0
        self.created_at = None
        self.updated_at = None
        
        if ad_id is not None:
            self.load()
    
    def get_connection(self):
        return mysql.connector.connect(
            host=self.config['host'],
            port=self.config['port'],
            database=self.config['database'],
            user=self.config['user'],
            password=self.config['password']
        )
    
    def load(self):
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT * FROM advertisements WHERE id = %s
        """, (self.ad_id,))
        
        result = cursor.fetchone()
        if result:
            self.copy = result['copy']
            self.start_date = result['start_date']
            self.end_date = result['end_date']
            self.status = result['status']
            self.impression_count = result['impression_count']
            self.max_impressions = result['max_impressions']
            self.created_at = result['created_at']
            self.updated_at = result['updated_at']
        
        cursor.close()
        conn.close()
        
        return self
    
    def save(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if self.ad_id:
            cursor.execute("""
                UPDATE advertisements 
                SET copy = %s, start_date = %s, end_date = %s, 
                    status = %s, max_impressions = %s
                WHERE id = %s
            """, (self.copy, self.start_date, self.end_date, 
                  self.status, self.max_impressions, self.ad_id))
        else:
            cursor.execute("""
                INSERT INTO advertisements 
                (copy, start_date, end_date, status, max_impressions)
                VALUES (%s, %s, %s, %s, %s)
            """, (self.copy, self.start_date, self.end_date, 
                  self.status, self.max_impressions))
            self.ad_id = cursor.lastrowid
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return self
    
    def record_impression(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE advertisements 
            SET impression_count = impression_count + 1
            WHERE id = %s
        """, (self.ad_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        self.impression_count += 1
    
    @staticmethod
    def get_active_ad():
        conn = Ad().get_connection()
        cursor = conn.cursor(dictionary=True)
        
        now = datetime.now()
        
        cursor.execute("""
            SELECT id FROM advertisements 
            WHERE status = 1 
            AND start_date <= %s 
            AND end_date >= %s
            AND (max_impressions = 0 OR impression_count < max_impressions)
            AND id != 0
            ORDER BY impression_count ASC, RAND()
            LIMIT 1
        """, (now, now))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            ad = Ad(result['id'])
            ad.record_impression()
            return ad
        else:
            ad = Ad(0)
            ad.record_impression()
            return ad
    
    @staticmethod
    def get_all_ads(include_inactive=False):
        conn = Ad().get_connection()
        cursor = conn.cursor(dictionary=True)
        
        if include_inactive:
            cursor.execute("SELECT * FROM advertisements ORDER BY id DESC")
        else:
            cursor.execute("""
                SELECT * FROM advertisements 
                WHERE status IN (0, 1) 
                ORDER BY id DESC
            """)
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return results
    
    def delete(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE advertisements 
            SET status = -1 
            WHERE id = %s
        """, (self.ad_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        self.status = -1
    
    def suspend(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE advertisements 
            SET status = -9 
            WHERE id = %s
        """, (self.ad_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        self.status = -9
    
    def activate(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE advertisements 
            SET status = 1 
            WHERE id = %s
        """, (self.ad_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        self.status = 1