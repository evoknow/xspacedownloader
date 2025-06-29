import mysql.connector
import json
import datetime
from typing import List, Dict, Optional, Any
import hashlib
import openai
import os
from .Email import Email

class Ticket:
    def __init__(self, db_config):
        self.db_config = db_config
        self.conn = None
        self.cursor = None
        self.connect()
        
    def connect(self):
        """Establish database connection"""
        try:
            # Remove unsupported parameters
            clean_config = self.db_config.copy()
            clean_config.pop('use_ssl', None)  # Remove use_ssl if present
            
            self.conn = mysql.connector.connect(**clean_config)
            self.cursor = self.conn.cursor(dictionary=True)
        except mysql.connector.Error as e:
            print(f"Database connection error: {e}")
            raise

    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def create_ticket(self, user_id: int, issue_title: str, issue_detail: str) -> Dict[str, Any]:
        """Create a new support ticket"""
        try:
            # Check if user is staff or admin (can create multiple tickets)
            self.cursor.execute("SELECT is_staff, is_admin FROM users WHERE id = %s", (user_id,))
            user = self.cursor.fetchone()
            
            if not user:
                return {"success": False, "error": "User not found"}
            
            is_privileged = user['is_staff'] or user['is_admin']
            
            # If not privileged user, check if they already have an open ticket
            if not is_privileged:
                self.cursor.execute("""
                    SELECT COUNT(*) as count FROM tickets 
                    WHERE user_id = %s AND status = 0
                """, (user_id,))
                result = self.cursor.fetchone()
                
                if result['count'] > 0:
                    return {"success": False, "error": "You already have an open ticket. Please add additional information to your existing ticket instead of creating a new one."}
            
            # Get AI priority and response
            ai_response = self.get_ai_priority_and_response(issue_title, issue_detail)
            priority = ai_response.get('priority', 0)
            initial_response = ai_response.get('response', '')
            
            # Create ticket
            now = datetime.datetime.now()
            response_json = json.dumps([{now.isoformat(): initial_response}]) if initial_response else json.dumps([])
            
            self.cursor.execute("""
                INSERT INTO tickets (user_id, issue_title, issue_detail, priority, opened_at, 
                                   last_updated_by_owner, response, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (user_id, issue_title, json.dumps({"detail": issue_detail}), 
                  priority, now, now, response_json, 0))
            
            self.conn.commit()
            ticket_id = self.cursor.lastrowid
            
            # Send email notifications for medium to critical priority
            if priority >= 1:
                self.send_new_ticket_notification(ticket_id, user_id, issue_title, priority)
            
            return {
                "success": True, 
                "ticket_id": ticket_id,
                "priority": priority,
                "ai_response": initial_response
            }
            
        except Exception as e:
            self.conn.rollback()
            return {"success": False, "error": str(e)}

    def get_ai_priority_and_response(self, issue_title: str, issue_detail: str) -> Dict[str, Any]:
        """Get AI-determined priority and potential response"""
        try:
            # Read knowledge base
            kb_content = ""
            kb_path = "/var/www/production/xspacedownload.com/website/xspacedownloader/KB.md"
            if os.path.exists(kb_path):
                with open(kb_path, 'r') as f:
                    kb_content = f.read()
            
            prompt = f"""As the support router AI for X Space Downloader with knowledge of the system per given knowledge data, identify the following issue's priority (0 - normal, 1 - medium, 2 - high, 3 - critical) and a potential response. If you have low confidence in responding to the issue based on the knowledge base information, just tell user that the issue will be reviewed by a human expert and responded as soon as possible. But if you are confident that you know the answer, please provide the answer.

Issue Title: {issue_title}
Issue Details: {issue_detail}

Knowledge Base:
{kb_content}

Respond in JSON format:
{{
    "priority": <0-3>,
    "response": "<your response to the user>",
    "confidence": "<high/medium/low>"
}}"""

            # Get OpenAI API key from environment or config
            api_key = os.environ.get('OPENAI_API_KEY', '')
            if not api_key:
                return {"priority": 0, "response": "Your ticket has been received and will be reviewed by support staff."}
            
            openai.api_key = api_key
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            ai_response = json.loads(response.choices[0].message.content)
            return ai_response
            
        except Exception as e:
            print(f"AI response error: {e}")
            return {"priority": 0, "response": "Your ticket has been received and will be reviewed by support staff."}

    def get_user_tickets(self, user_id: int, is_staff: bool = False, page: int = 1, per_page: int = 10) -> Dict[str, Any]:
        """Get tickets for a user or all tickets for staff"""
        try:
            offset = (page - 1) * per_page
            
            if is_staff:
                # Staff can see all tickets
                self.cursor.execute("""
                    SELECT t.*, u.email as user_email, u.display_name,
                           s.email as staff_email, s.display_name as staff_name
                    FROM tickets t
                    JOIN users u ON t.user_id = u.id
                    LEFT JOIN users s ON t.responded_by_staff_id = s.id
                    WHERE t.status >= -1
                    ORDER BY t.priority DESC, t.opened_at DESC
                    LIMIT %s OFFSET %s
                """, (per_page, offset))
                
                tickets = self.cursor.fetchall()
                
                self.cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE status >= -1")
            else:
                # Regular users see only their tickets
                self.cursor.execute("""
                    SELECT t.*, s.email as staff_email, s.display_name as staff_name
                    FROM tickets t
                    LEFT JOIN users s ON t.responded_by_staff_id = s.id
                    WHERE t.user_id = %s AND t.status >= -1
                    ORDER BY t.opened_at DESC
                    LIMIT %s OFFSET %s
                """, (user_id, per_page, offset))
                
                tickets = self.cursor.fetchall()
                
                self.cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE user_id = %s AND status >= -1", (user_id,))
            
            total = self.cursor.fetchone()['total']
            
            # Process tickets
            for ticket in tickets:
                ticket['opened_at'] = ticket['opened_at'].strftime("%m/%d/%Y %I:%M %p")
                if ticket['response_date']:
                    ticket['response_date'] = ticket['response_date'].strftime("%m/%d/%Y %I:%M %p")
                ticket['status_text'] = self.get_status_text(ticket['status'])
                ticket['priority_text'] = self.get_priority_text(ticket['priority'])
                
            return {
                "success": True,
                "tickets": tickets,
                "total": total,
                "page": page,
                "total_pages": (total + per_page - 1) // per_page
            }
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_ticket(self, ticket_id: int, user_id: int = None) -> Dict[str, Any]:
        """Get a specific ticket"""
        try:
            if user_id:
                self.cursor.execute("""
                    SELECT t.*, u.email as user_email, u.display_name,
                           s.email as staff_email, s.display_name as staff_name
                    FROM tickets t
                    JOIN users u ON t.user_id = u.id
                    LEFT JOIN users s ON t.responded_by_staff_id = s.id
                    WHERE t.id = %s AND (t.user_id = %s OR %s IN (
                        SELECT id FROM users WHERE is_staff = 1
                    ))
                """, (ticket_id, user_id, user_id))
            else:
                self.cursor.execute("""
                    SELECT t.*, u.email as user_email, u.display_name,
                           s.email as staff_email, s.display_name as staff_name
                    FROM tickets t
                    JOIN users u ON t.user_id = u.id
                    LEFT JOIN users s ON t.responded_by_staff_id = s.id
                    WHERE t.id = %s
                """, (ticket_id,))
            
            ticket = self.cursor.fetchone()
            
            if ticket:
                ticket['issue_detail'] = json.loads(ticket['issue_detail'])
                ticket['response'] = json.loads(ticket['response']) if ticket['response'] else []
                ticket['status_text'] = self.get_status_text(ticket['status'])
                ticket['priority_text'] = self.get_priority_text(ticket['priority'])
                
            return {"success": True, "ticket": ticket}
            
        except Exception as e:
            return {"success": False, "error": str(e)}

    def update_ticket(self, ticket_id: int, user_id: int, update_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update ticket details"""
        try:
            # Check if user owns the ticket or is staff
            self.cursor.execute("""
                SELECT user_id FROM tickets WHERE id = %s
            """, (ticket_id,))
            ticket = self.cursor.fetchone()
            
            if not ticket:
                return {"success": False, "error": "Ticket not found"}
            
            self.cursor.execute("SELECT is_staff FROM users WHERE id = %s", (user_id,))
            user = self.cursor.fetchone()
            
            if ticket['user_id'] != user_id and not user['is_staff']:
                return {"success": False, "error": "Unauthorized"}
            
            # Update ticket
            now = datetime.datetime.now()
            
            if 'issue_detail' in update_data:
                self.cursor.execute("""
                    UPDATE tickets 
                    SET issue_detail = %s, last_updated_by_owner = %s
                    WHERE id = %s
                """, (json.dumps({"detail": update_data['issue_detail']}), now, ticket_id))
            
            if 'status' in update_data:
                self.cursor.execute("""
                    UPDATE tickets 
                    SET status = %s
                    WHERE id = %s
                """, (update_data['status'], ticket_id))
            
            self.conn.commit()
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()
            return {"success": False, "error": str(e)}

    def add_user_update(self, ticket_id: int, user_id: int, additional_info: str) -> Dict[str, Any]:
        """Add additional information to a ticket by the user"""
        try:
            # Check if user owns the ticket
            self.cursor.execute("""
                SELECT user_id, issue_detail FROM tickets WHERE id = %s
            """, (ticket_id,))
            ticket = self.cursor.fetchone()
            
            if not ticket:
                return {"success": False, "error": "Ticket not found"}
            
            if ticket['user_id'] != user_id:
                return {"success": False, "error": "Unauthorized"}
            
            # Get current issue detail
            current_detail = json.loads(ticket['issue_detail'])
            
            # Add the new information with timestamp
            now = datetime.datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            
            # Create updates array if it doesn't exist
            if 'updates' not in current_detail:
                current_detail['updates'] = []
            
            # Add the new update
            current_detail['updates'].append({
                'timestamp': timestamp,
                'content': additional_info
            })
            
            # Update the ticket
            self.cursor.execute("""
                UPDATE tickets 
                SET issue_detail = %s, last_updated_by_owner = %s
                WHERE id = %s
            """, (json.dumps(current_detail), now, ticket_id))
            
            self.conn.commit()
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()
            return {"success": False, "error": str(e)}

    def add_response(self, ticket_id: int, staff_id: int, response_text: str) -> Dict[str, Any]:
        """Add a staff response to a ticket"""
        try:
            # Verify staff status
            self.cursor.execute("SELECT is_staff FROM users WHERE id = %s", (staff_id,))
            user = self.cursor.fetchone()
            
            if not user or not user['is_staff']:
                return {"success": False, "error": "Unauthorized"}
            
            # Get current ticket
            self.cursor.execute("SELECT response, user_id FROM tickets WHERE id = %s", (ticket_id,))
            ticket = self.cursor.fetchone()
            
            if not ticket:
                return {"success": False, "error": "Ticket not found"}
            
            # Update response
            now = datetime.datetime.now()
            responses = json.loads(ticket['response']) if ticket['response'] else []
            responses.append({now.isoformat(): response_text})
            
            self.cursor.execute("""
                UPDATE tickets 
                SET response = %s, responded_by_staff_id = %s, response_date = %s,
                    last_updated_by_staff = %s, status = 1
                WHERE id = %s
            """, (json.dumps(responses), staff_id, now, now, ticket_id))
            
            self.conn.commit()
            
            # Send email notification to user
            self.send_response_notification(ticket_id, ticket['user_id'])
            
            return {"success": True}
            
        except Exception as e:
            self.conn.rollback()
            return {"success": False, "error": str(e)}

    def get_previous_responses(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get previous responses for reuse"""
        try:
            self.cursor.execute("""
                SELECT DISTINCT response 
                FROM tickets 
                WHERE response IS NOT NULL AND response != '[]'
                ORDER BY last_updated_by_staff DESC
                LIMIT %s
            """, (limit,))
            
            all_responses = []
            for row in self.cursor.fetchall():
                responses = json.loads(row['response'])
                for response in responses:
                    for timestamp, text in response.items():
                        all_responses.append({
                            "timestamp": timestamp,
                            "text": text
                        })
            
            return all_responses[:limit]
            
        except Exception as e:
            print(f"Error getting previous responses: {e}")
            return []

    def send_new_ticket_notification(self, ticket_id: int, user_id: int, issue_title: str, priority: int):
        """Send email notification for new ticket"""
        try:
            # Get staff emails
            if priority == 3:  # Critical - notify staff and admins
                self.cursor.execute("""
                    SELECT email, display_name 
                    FROM users 
                    WHERE is_staff = 1 OR is_admin = 1
                """)
            else:  # Normal to high - notify only staff
                self.cursor.execute("""
                    SELECT email, display_name 
                    FROM users 
                    WHERE is_staff = 1
                """)
            
            staff_members = self.cursor.fetchall()
            
            # Get user info
            self.cursor.execute("SELECT email, display_name FROM users WHERE id = %s", (user_id,))
            user = self.cursor.fetchone()
            
            priority_text = self.get_priority_text(priority)
            
            for staff in staff_members:
                subject = f"[{priority_text}] New Support Ticket: {issue_title}"
                body = f"""
                <h3>New Support Ticket</h3>
                <p><strong>Priority:</strong> {priority_text}</p>
                <p><strong>From:</strong> {user['display_name'] or user['email']}</p>
                <p><strong>Title:</strong> {issue_title}</p>
                <p><a href="https://xspacedownload.com/tickets?id={ticket_id}">View and Respond to Ticket</a></p>
                """
                
                email = Email(self.db_config)
                email.send_email(staff['email'], subject, body)
                email.close()
                
        except Exception as e:
            print(f"Error sending new ticket notification: {e}")

    def send_response_notification(self, ticket_id: int, user_id: int):
        """Send email notification when ticket is responded to"""
        try:
            # Get user email
            self.cursor.execute("SELECT email, display_name FROM users WHERE id = %s", (user_id,))
            user = self.cursor.fetchone()
            
            # Get ticket info
            self.cursor.execute("SELECT issue_title FROM tickets WHERE id = %s", (ticket_id,))
            ticket = self.cursor.fetchone()
            
            subject = f"Response to Your Support Ticket: {ticket['issue_title']}"
            body = f"""
            <h3>Your Support Ticket Has Been Updated</h3>
            <p>A support staff member has responded to your ticket.</p>
            <p><strong>Title:</strong> {ticket['issue_title']}</p>
            <p><a href="https://xspacedownload.com/tickets?id={ticket_id}">View Response</a></p>
            <p><em>Note: This ticket will be automatically closed in 48 hours if no further communication is made.</em></p>
            """
            
            email = Email(self.db_config)
            email.send_email(user['email'], subject, body)
            email.close()
            
        except Exception as e:
            print(f"Error sending response notification: {e}")

    def auto_close_tickets(self):
        """Auto-close tickets that haven't been updated in 48 hours after staff response"""
        try:
            cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=48)
            
            self.cursor.execute("""
                UPDATE tickets 
                SET status = 2
                WHERE status = 1 
                AND response_date < %s
                AND (last_updated_by_owner < response_date OR last_updated_by_owner IS NULL)
            """, (cutoff_time,))
            
            self.conn.commit()
            
        except Exception as e:
            print(f"Error auto-closing tickets: {e}")

    def get_status_text(self, status: int) -> str:
        """Get human-readable status text"""
        status_map = {
            0: "Open",
            1: "Responded",
            2: "Closed",
            -1: "Deleted by Owner",
            -9: "Deleted by Staff",
            -6: "Archived"
        }
        return status_map.get(status, "Unknown")

    def get_priority_text(self, priority: int) -> str:
        """Get human-readable priority text"""
        priority_map = {
            0: "Normal",
            1: "Medium",
            2: "High",
            3: "Critical"
        }
        return priority_map.get(priority, "Normal")