#!/usr/bin/env python3
"""
Transcription Service Module
Core transcription and analysis functionality
"""

import os
import subprocess
import tempfile
import time
import smtplib
import glob
import shutil
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from pathlib import Path

try:
    import openai
    from dotenv import load_dotenv
    import yt_dlp
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.enums import TA_LEFT, TA_CENTER
except ImportError as e:
    print(f"Missing required package: {e}")
    raise

load_dotenv()

class TranscriptionService:
    """Service class for handling transcription and analysis operations"""
    
    def __init__(self, settings: Dict[str, Any] = None):
        """Initialize the transcription service with settings"""
        self.settings = settings or {}
        self.client = None
        # Run cleanup on initialization
        self.cleanup_on_startup()
        
    def load_api_key(self) -> str:
        """Load OpenAI API key from settings or environment"""
        api_key = self.settings.get('openai_api_key') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise EnvironmentError("OpenAI API key not found. Please configure in settings.")
        return api_key
    
    def get_client(self):
        """Get or create OpenAI client"""
        if not self.client:
            api_key = self.load_api_key()
            self.client = openai.OpenAI(api_key=api_key)
        return self.client
    
    def update_progress(self, job_id: str, progress: str, jobs_dict: Dict):
        """Update job progress"""
        if job_id in jobs_dict:
            jobs_dict[job_id]['progress'] = progress
    
    def cleanup_old_files(self, max_age_hours: int = 24):
        """Clean up old uploaded files and temporary directories"""
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            cutoff_timestamp = cutoff_time.timestamp()
            
            # Cleanup uploads directory
            uploads_dir = Path('uploads')
            if uploads_dir.exists():
                for file_path in uploads_dir.iterdir():
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff_timestamp:
                        file_path.unlink()
                        print(f"Cleaned up old upload: {file_path}")
            
            # Cleanup chunks directory
            chunks_dir = Path('chunks')
            if chunks_dir.exists():
                for chunk_dir in chunks_dir.iterdir():
                    if chunk_dir.is_dir() and chunk_dir.stat().st_mtime < cutoff_timestamp:
                        shutil.rmtree(chunk_dir)
                        print(f"Cleaned up old chunks: {chunk_dir}")
            
            # Cleanup audio directory (downloaded files)
            audio_dir = Path('audio')
            if audio_dir.exists():
                for file_path in audio_dir.iterdir():
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff_timestamp:
                        file_path.unlink()
                        print(f"Cleaned up old download: {file_path}")
            
            print(f"Auto-cleanup completed: removed files older than {max_age_hours} hours")
            
        except Exception as e:
            print(f"Auto-cleanup error: {e}")
    
    def cleanup_on_startup(self):
        """Run cleanup when service starts"""
        print("Running startup cleanup...")
        self.cleanup_old_files(max_age_hours=24)
    
    def cleanup_file_after_processing(self, file_path: str):
        """Clean up a specific file after processing is complete"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"Cleaned up processed file: {file_path}")
        except Exception as e:
            print(f"Failed to cleanup file {file_path}: {e}")
    
    def generate_html_report(self, analysis: str, transcript: str) -> str:
        """Generate HTML report for attachment"""
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Audio Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; line-height: 1.6; }}
        .header {{ background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
        .section {{ margin: 20px 0; padding: 20px; border-left: 4px solid #3498db; background-color: #f8f9fa; }}
        .transcript {{ background-color: #f9f9f9; padding: 15px; font-family: monospace; white-space: pre-wrap; border-radius: 5px; }}
        .analysis {{ background-color: #e8f5e8; padding: 15px; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Audio Analysis Report</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    
    <div class="section">
        <h2>Analysis Summary</h2>
        <div class="analysis">
            {analysis.replace(chr(10), '<br>')}
        </div>
    </div>
    
    <div class="section">
        <h2>Full Transcript</h2>
        <div class="transcript">
            {transcript}
        </div>
    </div>
</body>
</html>
        """
        return html_content
    
    def generate_pdf_report(self, analysis: str, transcript: str) -> bytes:
        """Generate PDF report for attachment"""
        try:
            buffer = tempfile.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []
            
            # Title
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=24,
                textColor='darkblue',
                alignment=TA_CENTER,
                spaceAfter=30
            )
            story.append(Paragraph("Audio Analysis Report", title_style))
            story.append(Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
            story.append(Spacer(1, 0.5*inch))
            
            # Analysis Section
            story.append(Paragraph("Analysis Summary", styles['Heading2']))
            story.append(Paragraph(analysis, styles['Normal']))
            story.append(Spacer(1, 0.3*inch))
            
            # Transcript Section
            story.append(Paragraph("Full Transcript", styles['Heading2']))
            story.append(Paragraph(transcript, styles['Normal']))
            
            doc.build(story)
            buffer.seek(0)
            return buffer.getvalue()
            
        except Exception as e:
            print(f"PDF generation error: {e}")
            return None
    
    def get_audio_duration(self, audio_path: str) -> float:
        """Get duration of audio file using ffprobe."""
        cmd = ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", 
               "-of", "csv=p=0", audio_path]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as e:
            raise RuntimeError(f"Could not determine audio duration: {e}")
    
    def extract_audio_from_video(self, video_path: str) -> str:
        """Extract audio from video file using ffmpeg."""
        temp_fd, temp_audio_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", 
            "-ar", "16000", "-ac", "1", "-b:a", "32k",
            temp_audio_path
        ]
        
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, timeout=300)
            if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
                raise RuntimeError("Audio extraction produced empty file")
            return temp_audio_path
        except subprocess.TimeoutExpired:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            raise RuntimeError("ffmpeg timed out during audio extraction")
        except subprocess.CalledProcessError as e:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            raise RuntimeError(f"ffmpeg failed: {e.stderr.decode()}")
    
    def extract_audio_chunk(self, video_path: str, start_time: float, duration: float) -> str:
        """Extract a chunk of audio from video using ffmpeg."""
        temp_fd, temp_audio_path = tempfile.mkstemp(suffix=".mp3")
        os.close(temp_fd)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", video_path,
            "-vn",
            "-acodec", "libmp3lame",
            "-ar", "16000",
            "-ac", "1",
            "-b:a", "32k",
            temp_audio_path
        ]
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE, timeout=120)
            
            if not os.path.exists(temp_audio_path) or os.path.getsize(temp_audio_path) == 0:
                raise RuntimeError("Audio extraction produced empty file")
            
            return temp_audio_path
        except subprocess.TimeoutExpired:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            raise RuntimeError("ffmpeg timed out while extracting audio chunk")
        except subprocess.CalledProcessError as e:
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            raise RuntimeError(f"ffmpeg audio extraction failed: {e.stderr.decode()}")
    
    def get_audio_chunks(self, audio_path: str, max_duration: float = 600) -> list:
        """Split audio into chunks for processing."""
        duration = self.get_audio_duration(audio_path)
        
        if duration <= 600:  # 10 minutes
            return [(0, duration + 0.5)]
        
        chunks = []
        start = 0
        overlap = 10
        
        while start < duration:
            remaining = duration - start
            chunk_duration = min(max_duration, remaining)
            
            if remaining <= (max_duration + overlap):
                chunk_duration = remaining + 0.5
                
            chunks.append((start, chunk_duration))
            
            if start + chunk_duration >= duration:
                break
                
            start += max_duration - overlap
        
        return chunks
    
    def download_from_url(self, url: str, job_id: str = None, jobs_dict: Dict = None) -> str:
        """Download audio/video from URL using yt-dlp"""
        if jobs_dict and job_id:
            self.update_progress(job_id, "Downloading from URL...", jobs_dict)
        
        os.makedirs("audio", exist_ok=True)
        outtmpl = "audio/downloaded_%(title)s.%(ext)s"
        
        # Enhanced yt-dlp command with better error handling and YouTube protection bypass
        cmd = [
            "yt-dlp", 
            "-x", 
            "--audio-format", "mp3",
            "--no-check-certificate",
            "--prefer-insecure",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "--referer", "https://www.youtube.com/",
            "--add-header", "Accept-Language:en-US,en;q=0.9",
            url, 
            "-o", outtmpl
        ]
        
        try:
            result = subprocess.run(cmd, check=True, timeout=600, capture_output=True, text=True)
            
            import glob
            mp3_files = glob.glob("audio/downloaded_*.mp3")
            if not mp3_files:
                raise RuntimeError("No audio files were downloaded. The URL might not contain audio content or may require authentication.")
            return max(mp3_files, key=os.path.getctime)
            
        except subprocess.CalledProcessError as e:
            error_output = e.stderr if e.stderr else str(e)
            if "Sign in to confirm you're not a bot" in error_output:
                raise RuntimeError("YouTube requires authentication for this video. Please try a different video or use a direct audio file URL instead.")
            elif "Video unavailable" in error_output:
                raise RuntimeError("Video is unavailable or has been removed.")
            elif "Private video" in error_output:
                raise RuntimeError("Video is private and cannot be accessed.")
            else:
                raise RuntimeError(f"Download failed: {error_output}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Download timed out after 10 minutes. The file might be too large or the connection is slow.")
    
    def transcribe_audio(self, input_path: str, model: str = "whisper-1", 
                        job_id: str = None, jobs_dict: Dict = None) -> str:
        """Transcribe audio file using OpenAI Whisper API."""
        temp_paths = []
        
        try:
            if jobs_dict and job_id:
                self.update_progress(job_id, "Starting transcription...", jobs_dict)
            
            if not os.path.exists(input_path):
                raise FileNotFoundError(f"Input file not found: {input_path}")
            
            file_size = os.path.getsize(input_path)
            print(f"Processing file: {os.path.basename(input_path)} ({file_size:,} bytes)")
            
            client = self.get_client()
            
            # Test API connection
            try:
                models = client.models.list()
                print("OpenAI API connection successful")
            except Exception as e:
                raise RuntimeError(f"Failed to connect to OpenAI API: {e}")
            
            chunks = self.get_audio_chunks(input_path)
            transcript_parts = []
            
            print(f"Audio will be processed in {len(chunks)} chunk(s)")
            
            for i, (start, chunk_duration) in enumerate(chunks):
                if jobs_dict and job_id:
                    self.update_progress(job_id, f"Processing chunk {i+1}/{len(chunks)}...", jobs_dict)
                
                print(f"Processing chunk {i+1}/{len(chunks)}")
                print(f"Time range: {int(start)}s to {int(start+chunk_duration)}s")
                
                try:
                    temp_chunk_path = self.extract_audio_chunk(input_path, start, chunk_duration)
                    temp_paths.append(temp_chunk_path)
                    
                    with open(temp_chunk_path, "rb") as audio_file:
                        file_size = os.path.getsize(temp_chunk_path)
                        print(f"Uploading chunk {i+1} to OpenAI ({file_size:,} bytes)")
                        
                        start_time = time.time()
                        
                        transcript = client.audio.transcriptions.create(
                            model=model,
                            file=audio_file
                        )
                        
                        elapsed = time.time() - start_time
                        print(f"Chunk {i+1} completed: {len(transcript.text)} characters ({elapsed:.1f}s)")
                        
                        transcript_parts.append(transcript.text)
                        
                except Exception as e:
                    print(f"Error processing chunk {i+1}: {e}")
                    raise RuntimeError(f"Failed to process audio chunk {i+1}/{len(chunks)}: {e}")
                
                if temp_chunk_path and os.path.exists(temp_chunk_path):
                    os.remove(temp_chunk_path)
            
            return "\n\n".join(transcript_parts)
            
        finally:
            for p in temp_paths:
                if p and os.path.exists(p):
                    os.remove(p)
    
    def create_financial_summary(self, transcript: str, model: str = "gpt-4o") -> str:
        """Create focused financial summary with macro themes and trade ideas."""
        client = self.get_client()
        
        print(f"Creating analysis with model: {model}")
        print(f"Transcript length: {len(transcript):,} characters")
        
        analysis_prompt = """You are a senior financial analyst specializing in macro themes and market insights. Analyze this audio transcript and create a comprehensive investment research report.

STRUCTURE YOUR ANALYSIS AS FOLLOWS:

## EXECUTIVE SUMMARY
Brief 2-3 sentence overview of key investment themes

## KEY THEMES & MARKET INSIGHTS
- Identify and elaborate on 3-5 major macro themes
- Include specific market sectors, geographies, or asset classes mentioned
- Note any timeline or catalyst mentions

## TRADE IDEAS & INVESTMENT OPPORTUNITIES
- Extract specific trade ideas, stock picks, or investment strategies
- Include any mentioned price targets, entry/exit points
- Note risk management suggestions

## SUPPORTING EVIDENCE & QUOTES
For each major point, include relevant quotes from the original audio to support your analysis.

## RISK FACTORS
- Key risks or concerns mentioned
- Market or economic headwinds discussed

Focus on actionable insights for institutional investors. Be specific about sectors, companies, and timeframes when mentioned. If specific numbers, dates, or targets are mentioned, include them prominently."""

        try:
            start_time = time.time()
            
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": analysis_prompt},
                    {"role": "user", "content": f"Please analyze this financial audio transcript:\n\n{transcript}"}
                ],
                max_tokens=4000,
                temperature=0.1
            )
            
            elapsed = time.time() - start_time
            analysis = response.choices[0].message.content
            print(f"Analysis completed: {len(analysis)} characters ({elapsed:.1f}s)")
            
            return analysis
            
        except Exception as e:
            raise RuntimeError(f"Failed to create financial analysis: {e}")
    
    def send_email_report(self, analysis: str, transcript: str, 
                         subject: str = "Audio Analysis Report") -> Dict[str, Any]:
        """Send email report with summary in body and detailed attachments"""
        try:
            # Get email settings
            email_address = self.settings.get('email_address')
            email_password = self.settings.get('email_password')
            output_email = self.settings.get('output_email')
            
            if not all([email_address, email_password, output_email]):
                return {'success': False, 'message': 'Email configuration incomplete'}
            
            # Create email
            msg = MIMEMultipart()
            msg['From'] = email_address
            msg['To'] = output_email
            msg['Subject'] = subject
            
            # Extract summary from analysis (first few paragraphs)
            analysis_lines = analysis.split('\n')
            summary_lines = []
            for line in analysis_lines[:15]:  # First 15 lines as summary
                if line.strip():
                    summary_lines.append(line.strip())
                if len(summary_lines) >= 8:  # Limit summary to 8 meaningful lines
                    break
            
            summary = '\n'.join(summary_lines)
            if len(analysis_lines) > 15:
                summary += '\n\n[See attached files for complete analysis and transcript]'
            
            # Email body with summary only
            body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; margin: 20px;">
            <div style="background-color: #2c3e50; color: white; padding: 20px; border-radius: 5px;">
                <h2 style="margin: 0;">Audio Analysis Report</h2>
                <p style="margin: 5px 0 0 0;"><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            </div>
            
            <div style="background-color: #e8f5e8; padding: 20px; margin: 20px 0; border-radius: 5px; border-left: 4px solid #27ae60;">
                <h3 style="color: #27ae60; margin-top: 0;">Summary</h3>
                <div style="white-space: pre-line; line-height: 1.6;">
{summary}
                </div>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; border-left: 4px solid #3498db;">
                <p><strong>📎 Attachments:</strong></p>
                <ul>
                    <li><strong>complete_analysis.html</strong> - Full analysis with formatting</li>
                    <li><strong>complete_analysis.pdf</strong> - PDF version for printing/sharing</li>
                </ul>
                <p style="color: #666; font-size: 0.9em;">Open the attachments to view the complete analysis and full transcript.</p>
            </div>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(body, 'html'))
            
            # Generate and attach HTML report
            html_content = self.generate_html_report(analysis, transcript)
            html_attachment = MIMEApplication(html_content.encode('utf-8'), _subtype='html')
            html_attachment.add_header('Content-Disposition', 'attachment', filename='complete_analysis.html')
            msg.attach(html_attachment)
            
            # Generate and attach PDF report
            pdf_content = self.generate_pdf_report(analysis, transcript)
            if pdf_content:
                pdf_attachment = MIMEApplication(pdf_content, _subtype='pdf')
                pdf_attachment.add_header('Content-Disposition', 'attachment', filename='complete_analysis.pdf')
                msg.attach(pdf_attachment)
            
            # Send email
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(email_address, email_password)
                server.send_message(msg)
            
            return {'success': True, 'message': 'Email sent successfully with attachments'}
            
        except Exception as e:
            return {'success': False, 'message': f'Email failed: {str(e)}'}
    
    def test_email_credentials(self) -> Dict[str, Any]:
        """Test email credentials"""
        try:
            email_address = self.settings.get('email_address')
            email_password = self.settings.get('email_password')
            
            if not email_address or not email_password:
                return {'success': False, 'message': 'Email credentials not configured'}
            
            with smtplib.SMTP('smtp.gmail.com', 587) as server:
                server.starttls()
                server.login(email_address, email_password)
            
            return {'success': True, 'message': 'Email credentials verified successfully'}
            
        except Exception as e:
            return {'success': False, 'message': f'Email test failed: {str(e)}'}
    
    def process_file(self, file_path: str, job_id: str = None, jobs_dict: Dict = None) -> Dict[str, Any]:
        """Process uploaded file with auto-cleanup"""
        try:
            # Run cleanup on each processing cycle
            self.cleanup_old_files(max_age_hours=24)
            
            # Transcribe
            self.update_progress(job_id, "Transcribing audio...", jobs_dict)
            transcript = self.transcribe_audio(file_path, job_id=job_id, jobs_dict=jobs_dict)
            
            # Analyze
            self.update_progress(job_id, "Creating financial analysis...", jobs_dict)
            analysis = self.create_financial_summary(transcript)
            
            # Send email if configured
            email_result = None
            if self.settings.get('send_email', False):
                self.update_progress(job_id, "Sending email report...", jobs_dict)
                email_result = self.send_email_report(analysis, transcript)
            
            return {
                'transcript': transcript,
                'analysis': analysis,
                'email_result': email_result
            }
            
        except Exception as e:
            raise RuntimeError(f"Processing failed: {str(e)}")
        finally:
            # Clean up the processed file to save space
            if file_path and os.path.exists(file_path):
                self.cleanup_file_after_processing(file_path)
    
    def process_url(self, url: str, job_id: str = None, jobs_dict: Dict = None) -> Dict[str, Any]:
        """Process URL"""
        try:
            # Download
            downloaded_file = self.download_from_url(url, job_id=job_id, jobs_dict=jobs_dict)
            
            try:
                # Process the downloaded file
                result = self.process_file(downloaded_file, job_id=job_id, jobs_dict=jobs_dict)
                return result
                
            finally:
                # Clean up downloaded file after processing
                if downloaded_file and os.path.exists(downloaded_file):
                    self.cleanup_file_after_processing(downloaded_file)
                    
        except Exception as e:
            raise RuntimeError(f"URL processing failed: {str(e)}")