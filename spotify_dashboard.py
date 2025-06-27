#!/usr/bin/env python3
"""
Script to generate a static web dashboard for your Spotify statistics.

This script:
1. Runs the spotify_stats.py script to generate statistics if needed
2. Sets up a simple HTTP server to view the dashboard locally
3. Provides instructions for deploying to AWS S3 and CloudFront

Requirements:
- Python 3.6+
- Generated statistics from spotify_stats.py
"""

import os
import sys
import subprocess
import webbrowser
import http.server
import socketserver
import json
import shutil
import argparse
import time
import datetime
from pathlib import Path
import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform color support
colorama.init(autoreset=True)

# Define paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(SCRIPT_DIR, "dashboard")
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
STATS_SCRIPT = os.path.join(SCRIPT_DIR, "spotify_stats.py")
DEPLOY_DIR = os.path.join(SCRIPT_DIR, "deploy")

def print_header(text):
    """Print a formatted header."""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}" + "="*50)
    print(f"{Fore.CYAN}{Style.BRIGHT}{text}")
    print(f"{Fore.CYAN}{Style.BRIGHT}" + "="*50)

def print_success(text):
    """Print a success message."""
    print(f"{Fore.GREEN}{text}")

def print_error(text):
    """Print an error message."""
    print(f"{Fore.RED}{text}")

def print_warning(text):
    """Print a warning message."""
    print(f"{Fore.YELLOW}{text}")

def print_info(text):
    """Print an info message."""
    print(f"{Fore.BLUE}{text}")

def check_stats_freshness():
    """Check if statistics are fresh or need to be regenerated."""
    # Check if data directory exists
    if not os.path.exists(DATA_DIR):
        return False
    
    # Check for key data files
    required_files = [
        "top_artists.csv",
        "top_tracks.csv",
        "top_genres.csv",
        "spotify_stats.json"
    ]
    
    for file in required_files:
        file_path = os.path.join(DATA_DIR, file)
        if not os.path.exists(file_path):
            return False
    
    # Check the age of the data
    try:
        # Get the modification time of the top_artists.csv file
        stats_time = os.path.getmtime(os.path.join(DATA_DIR, "top_artists.csv"))
        current_time = time.time()
        
        # Calculate age in days
        age_days = (current_time - stats_time) / (24 * 60 * 60)
        
        # Return the age for the caller to decide if it's fresh enough
        return {
            "fresh": True,
            "age_days": age_days,
            "last_updated": datetime.datetime.fromtimestamp(stats_time).strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception:
        return False

def run_stats_script():
    """Run the spotify_stats.py script to generate statistics."""
    print_info("Generating Spotify statistics...")
    
    # Check if the script exists
    if not os.path.exists(STATS_SCRIPT):
        print_error(f"Error: Could not find {STATS_SCRIPT}")
        return False
    
    # Run the script
    try:
        subprocess.run([sys.executable, STATS_SCRIPT], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Error running statistics script: {e}")
        return False

def generate_dashboard_data():
    """Generate the data needed for the dashboard."""
    # Check if data directory exists
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)
    
    # Check if dashboard directory exists
    if not os.path.exists(DASHBOARD_DIR):
        print_error(f"Error: Dashboard directory not found at {DASHBOARD_DIR}")
        print_info("Creating dashboard directory...")
        os.makedirs(DASHBOARD_DIR, exist_ok=True)
        
        # Create a basic index.html file
        index_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Spotify Music Dashboard</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #121212;
            color: #ffffff;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1, h2 {
            color: #1DB954;
        }
        .card {
            background-color: #181818;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }
        .error {
            color: #ff5555;
            padding: 20px;
            background-color: #181818;
            border-radius: 8px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Spotify Music Dashboard</h1>
        <div class="error">
            <h2>Error Loading Data</h2>
            <p>Could not load your Spotify data. Please make sure you've run the spotify_stats.py script first.</p>
        </div>
    </div>
</body>
</html>
"""
        
        with open(os.path.join(DASHBOARD_DIR, "index.html"), "w") as f:
            f.write(index_html)
    
    # Check for required data files
    required_files = [
        "top_artists.csv",
        "top_tracks.csv",
        "top_genres.csv",
        "spotify_stats.json"
    ]
    
    missing_files = []
    for file in required_files:
        file_path = os.path.join(DATA_DIR, file)
        if not os.path.exists(file_path):
            missing_files.append(file)
    
    if missing_files:
        print_warning(f"Missing data files: {', '.join(missing_files)}")
        print_info("Regenerating statistics...")
        if not run_stats_script():
            return False
    
    # Copy data files to dashboard directory
    data_dashboard_dir = os.path.join(DASHBOARD_DIR, "data")
    os.makedirs(data_dashboard_dir, exist_ok=True)
    
    for file in os.listdir(DATA_DIR):
        if file.endswith(".json") or file.endswith(".csv"):
            try:
                shutil.copy2(
                    os.path.join(DATA_DIR, file),
                    os.path.join(data_dashboard_dir, file)
                )
            except Exception as e:
                print_warning(f"Could not copy {file}: {e}")
    
    return True

def start_local_server():
    """Start a local HTTP server to view the dashboard."""
    # Check if dashboard directory exists
    if not os.path.exists(DASHBOARD_DIR):
        print_error(f"Error: Dashboard directory not found at {DASHBOARD_DIR}")
        return False
    
    # Create data directory in dashboard if it doesn't exist
    data_dashboard_dir = os.path.join(DASHBOARD_DIR, "data")
    os.makedirs(data_dashboard_dir, exist_ok=True)
    
    # Copy latest data files to dashboard directory
    print_info("Copying latest data files to dashboard...")
    for file in os.listdir(DATA_DIR):
        if file.endswith(".json") or file.endswith(".csv"):
            try:
                shutil.copy2(
                    os.path.join(DATA_DIR, file),
                    os.path.join(data_dashboard_dir, file)
                )
            except Exception as e:
                print_warning(f"Could not copy {file}: {e}")
    
    # Start server
    try:
        # Set up server
        port = 8000
        handler = http.server.SimpleHTTPRequestHandler
        
        # Change to dashboard directory
        os.chdir(DASHBOARD_DIR)
        
        # Create server
        with socketserver.TCPServer(("", port), handler) as httpd:
            print_success(f"Server started at http://localhost:{port}")
            print_info("Opening dashboard in your default web browser...")
            
            # Open browser
            webbrowser.open(f"http://localhost:{port}")
            
            print_warning("Press Ctrl+C to stop the server and return to the menu.")
            
            # Serve until interrupted
            httpd.serve_forever()
    except KeyboardInterrupt:
        print_info("\nServer stopped.")
        return True
    except Exception as e:
        print_error(f"Error starting server: {e}")
        return False

def prepare_for_aws_deployment():
    """Prepare the dashboard for AWS deployment."""
    print_header("Preparing Dashboard for AWS Deployment")
    
    # Check if dashboard directory exists
    if not os.path.exists(DASHBOARD_DIR):
        print_error(f"Error: Dashboard directory not found at {DASHBOARD_DIR}")
        return False
    
    # Create deploy directory if it doesn't exist
    if not os.path.exists(DEPLOY_DIR):
        os.makedirs(DEPLOY_DIR, exist_ok=True)
    
    try:
        # Copy dashboard files to deploy directory
        print_info("Copying dashboard files to deploy directory...")
        
        # Copy HTML files
        for html_file in os.listdir(DASHBOARD_DIR):
            if html_file.endswith(".html"):
                shutil.copy2(
                    os.path.join(DASHBOARD_DIR, html_file),
                    os.path.join(DEPLOY_DIR, html_file)
                )
        
        # Create assets directory
        assets_dir = os.path.join(DEPLOY_DIR, "assets")
        os.makedirs(assets_dir, exist_ok=True)
        
        # Copy CSS and JS files
        dashboard_assets = os.path.join(DASHBOARD_DIR, "assets")
        if os.path.exists(dashboard_assets):
            for asset_file in os.listdir(dashboard_assets):
                shutil.copy2(
                    os.path.join(dashboard_assets, asset_file),
                    os.path.join(assets_dir, asset_file)
                )
        
        # Create data directory
        data_deploy_dir = os.path.join(DEPLOY_DIR, "data")
        os.makedirs(data_deploy_dir, exist_ok=True)
        
        # Copy data files
        for data_file in os.listdir(DATA_DIR):
            if data_file.endswith(".json"):
                shutil.copy2(
                    os.path.join(DATA_DIR, data_file),
                    os.path.join(data_deploy_dir, data_file)
                )
        
        print_success("Dashboard prepared for deployment.")
        
        # Show AWS deployment instructions
        print_info("\nTo deploy to AWS S3:")
        print("1. Create an S3 bucket (e.g., 'my-spotify-dashboard')")
        print("2. Enable static website hosting on the bucket")
        print("3. Upload the contents of the deploy directory to your S3 bucket:")
        print(f"   aws s3 sync {DEPLOY_DIR} s3://my-spotify-dashboard --acl public-read")
        print("\nOptional: Set up CloudFront for faster delivery:")
        print("1. Create a CloudFront distribution pointing to your S3 bucket")
        print("2. Use the CloudFront domain to access your dashboard")
        
        return True
    except Exception as e:
        print_error(f"Error preparing for deployment: {e}")
        return False

def main():
    """Main function."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Generate and view Spotify statistics dashboard.")
    parser.add_argument("--deploy", action="store_true", help="Prepare dashboard for AWS deployment")
    args = parser.parse_args()
    
    # Check if we're preparing for deployment
    if args.deploy:
        # Generate dashboard data
        if generate_dashboard_data():
            # Prepare for AWS deployment
            prepare_for_aws_deployment()
        return
    
    # Ask if user wants to regenerate statistics
    stats_info = check_stats_freshness()
    if stats_info and stats_info['fresh']:
        print_info(f"Found existing statistics (last updated: {stats_info['last_updated']}).")
        print_info(f"Statistics are {stats_info['age_days']:.1f} days old.")
        
        regenerate = input("Would you like to regenerate statistics? (y/n): ").strip().lower()
        if regenerate == 'y':
            print_info("Regenerating statistics...")
            if not run_stats_script():
                print_error("Failed to regenerate statistics.")
                return
            print_success("Statistics regenerated successfully.")
    else:
        print_info("No existing statistics found or statistics are outdated.")
        print_info("Generating new statistics...")
        if not run_stats_script():
            print_error("Failed to generate statistics.")
            return
        print_success("Statistics generated successfully.")
    
    # Generate dashboard data
    if not generate_dashboard_data():
        return
    
    # Start local server
    start_local_server()

if __name__ == "__main__":
    main()
