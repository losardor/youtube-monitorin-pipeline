# Server Migration Guide - YouTube Monitoring Pipeline

## Part 1: Package Your Project

### 1. Create Deployment Package

On your local machine:

```bash
cd /Users/losardo/Documents/Youtube/youtube_monitoring_pipeline

# Create a clean package (exclude venv, cache, databases)
tar -czf youtube_pipeline.tar.gz \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='*.db' \
    --exclude='data/raw' \
    --exclude='data/processed' \
    --exclude='.DS_Store' \
    src/ config/ data/sources.csv \
    collect_comprehensive.py collect.py view_data.py \
    requirements.txt README.md

# Verify package
tar -tzf youtube_pipeline.tar.gz | head -20
```

### 2. Copy API Key to Comprehensive Config

Before packaging, update your API key:
```bash
# Copy your working API key to the new config
cp config/config.yaml config/config_comprehensive.yaml

# Then edit config_comprehensive.yaml to use comprehensive settings
nano config/config_comprehensive.yaml
```

---

## Part 2: Server Setup (Ubuntu/Debian)

### 1. Choose a Server

**Recommended specs for 12,847 channels:**
- **CPU**: 2-4 cores
- **RAM**: 4-8 GB
- **Storage**: 50-100 GB SSD
- **Bandwidth**: Unlimited or high limit

**Cloud options:**
- DigitalOcean: $24/month (4GB RAM, 2 CPUs)
- AWS EC2: t3.medium ($30-40/month)
- Hetzner: €9/month (4GB RAM, 2 CPUs) - best value
- Google Cloud: e2-medium ($24/month)

### 2. Initial Server Setup

SSH into your server:
```bash
ssh root@YOUR_SERVER_IP
```

Update system:
```bash
apt update && apt upgrade -y
```

Install Python and dependencies:
```bash
# Install Python 3.11
apt install -y python3.11 python3.11-venv python3-pip

# Install system dependencies
apt install -y git curl wget screen htop

# Optional: Install PostgreSQL for larger datasets
# apt install -y postgresql postgresql-contrib

# Create non-root user (recommended)
adduser youtube_collector
usermod -aG sudo youtube_collector

# Switch to new user
su - youtube_collector
```

### 3. Upload and Extract Project

**Option A: Using SCP (from your local machine):**
```bash
# From your local machine
scp youtube_pipeline.tar.gz youtube_collector@YOUR_SERVER_IP:~/

# Then on server:
cd ~
tar -xzf youtube_pipeline.tar.gz
cd youtube_monitoring_pipeline
```

**Option B: Using Git (if you have a private repo):**
```bash
git clone YOUR_PRIVATE_REPO
cd youtube_monitoring_pipeline
```

**Option C: Using wget (if uploaded to cloud storage):**
```bash
wget https://your-storage-url/youtube_pipeline.tar.gz
tar -xzf youtube_pipeline.tar.gz
cd youtube_monitoring_pipeline
```

### 4. Setup Python Environment

```bash
cd ~/youtube_monitoring_pipeline

# Create virtual environment with Python 3.11
python3.11 -m venv venv

# Activate
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "from googleapiclient.discovery import build; print('✓ Google API installed')"
python -c "import pandas; print('✓ Pandas installed')"
python -c "import yaml; print('✓ PyYAML installed')"
```

### 5. Configure for Server

```bash
# Create necessary directories
mkdir -p data/raw data/processed data/checkpoints logs

# Edit config with your API key (if not already done)
nano config/config_comprehensive.yaml

# Test API connection
python -c "
import yaml
with open('config/config_comprehensive.yaml') as f:
    config = yaml.safe_load(f)
print('API Key configured:', config['api']['youtube_api_key'][:10] + '...')
"
```

---

## Part 3: Running Long-Duration Collections

### Using Screen (Recommended for Beginners)

**Start a collection:**
```bash
# Start a screen session
screen -S youtube_collection

# Activate venv
source venv/bin/activate

# Start comprehensive collection
python collect_comprehensive.py --sources data/sources.csv --config config/config_comprehensive.yaml

# Detach from screen: Press Ctrl+A, then D
```

**Monitor the collection:**
```bash
# Reattach to see progress
screen -r youtube_collection

# Detach again: Ctrl+A, then D

# List all screen sessions
screen -ls

# Kill a session (if needed)
screen -X -S youtube_collection quit
```

### Using Tmux (More Advanced)

```bash
# Install tmux
sudo apt install tmux

# Start tmux session
tmux new -s youtube_collection

# Run collection
source venv/bin/activate
python collect_comprehensive.py --sources data/sources.csv

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t youtube_collection
```

### Using nohup (Simplest)

```bash
# Run in background, immune to hangups
nohup python collect_comprehensive.py \
    --sources data/sources.csv \
    --config config/config_comprehensive.yaml \
    > logs/collection_output.log 2>&1 &

# Get process ID
echo $!  # Save this number

# Monitor progress
tail -f logs/collection_output.log

# Check if still running
ps aux | grep collect_comprehensive

# Kill if needed
kill PROCESS_ID
```

---

## Part 4: Monitoring and Management

### 1. Create Monitoring Script

```bash
# Create monitoring script
cat > monitor.sh << 'EOF'
#!/bin/bash
echo "==================================="
echo "YouTube Collection Monitor"
echo "==================================="
echo ""

# Check if collection is running
if pgrep -f "collect_comprehensive.py" > /dev/null; then
    echo "✓ Collection is RUNNING"
    PID=$(pgrep -f "collect_comprehensive.py")
    echo "  Process ID: $PID"
    echo "  CPU/Memory:"
    ps -p $PID -o %cpu,%mem,etime,cmd
else
    echo "✗ Collection is NOT running"
fi

echo ""
echo "Latest stats from database:"
python3 view_data.py --stats 2>/dev/null || echo "  (Run from project directory)"

echo ""
echo "Recent log entries:"
tail -5 logs/pipeline.log 2>/dev/null || echo "  (No logs yet)"

echo ""
echo "Disk usage:"
df -h . | tail -1
EOF

chmod +x monitor.sh

# Run monitor
./monitor.sh
```

### 2. Auto-Resume Script

```bash
# Create auto-resume script for daily runs
cat > daily_collection.sh << 'EOF'
#!/bin/bash
cd ~/youtube_monitoring_pipeline
source venv/bin/activate

# Run with resume flag
python collect_comprehensive.py \
    --sources data/sources.csv \
    --config config/config_comprehensive.yaml \
    --resume \
    >> logs/daily_run_$(date +%Y%m%d).log 2>&1
EOF

chmod +x daily_collection.sh

# Add to crontab (run daily at 2 AM)
crontab -e
# Add this line:
# 0 2 * * * /home/youtube_collector/youtube_monitoring_pipeline/daily_collection.sh
```

### 3. Export Data Remotely

```bash
# Create export script
cat > export_data.sh << 'EOF'
#!/bin/bash
echo "Exporting database to CSV..."
source venv/bin/activate

python3 << PYEOF
from src.database import Database
db = Database('data/youtube_monitoring.db')
print("Exporting channels...")
db.export_to_csv('channels', 'data/processed/channels.csv')
print("Exporting videos...")
db.export_to_csv('videos', 'data/processed/videos.csv')
print("Exporting comments...")
db.export_to_csv('comments', 'data/processed/comments.csv')
print("✓ Export complete!")
PYEOF

# Create archive
tar -czf exports_$(date +%Y%m%d).tar.gz data/processed/*.csv
echo "✓ Archive created: exports_$(date +%Y%m%d).tar.gz"
EOF

chmod +x export_data.sh
```

### 4. Download Results to Local Machine

```bash
# From your local machine:

# Download database
scp youtube_collector@YOUR_SERVER_IP:~/youtube_monitoring_pipeline/data/youtube_monitoring.db .

# Download exports
scp youtube_collector@YOUR_SERVER_IP:~/youtube_monitoring_pipeline/exports_*.tar.gz .

# Download logs
scp youtube_collector@YOUR_SERVER_IP:~/youtube_monitoring_pipeline/logs/pipeline.log .
```

---

## Part 5: Comprehensive Collection Strategy

### Timeline Estimates (with 1M quota/day)

**Quota usage for comprehensive collection:**
- Average: ~140 units per channel (all videos + all comments)
- Daily capacity: ~7,000 channels with 1M quota
- Total time for 12,847 channels: **~2 days**

### Recommended Approach

**Day 1: Setup and Test**
```bash
# Test with 10 channels
python collect_comprehensive.py --sources data/sources.csv --max-channels 10

# Check results
python view_data.py --stats

# If good, start full collection
screen -S youtube_collection
python collect_comprehensive.py --sources data/sources.csv
# Detach: Ctrl+A, D
```

**Day 2-3: Monitor**
```bash
# Check progress periodically
./monitor.sh

# Or tail logs
tail -f logs/pipeline.log

# Reattach to see live output
screen -r youtube_collection
```

**Day 4: Export and Download**
```bash
# Export data
./export_data.sh

# Download to local machine
scp youtube_collector@YOUR_SERVER_IP:~/youtube_monitoring_pipeline/exports_*.tar.gz .
```

---

## Part 6: Troubleshooting

### Collection Stopped?

```bash
# Check if running
./monitor.sh

# Check logs for errors
tail -100 logs/pipeline.log

# Resume from checkpoint
screen -S youtube_collection
source venv/bin/activate
python collect_comprehensive.py --sources data/sources.csv --resume
```

### Out of Disk Space?

```bash
# Check space
df -h

# Clear old logs
find logs/ -name "*.log" -mtime +7 -delete

# Compress old data
tar -czf backup_$(date +%Y%m%d).tar.gz data/processed/*.csv
rm data/processed/*.csv
```

### Quota Exceeded?

```bash
# Check current quota usage
python3 << EOF
from src.database import Database
db = Database('data/youtube_monitoring.db')
cursor = db.cursor
cursor.execute('SELECT SUM(quota_used) FROM collection_runs WHERE DATE(start_time) = DATE("now")')
print(f"Today's quota: {cursor.fetchone()[0]} units")
EOF

# Wait for reset (midnight Pacific Time)
# Or continue tomorrow with --resume
```

---

## Part 7: Security Best Practices

```bash
# Set up firewall
sudo ufw allow ssh
sudo ufw enable

# Secure SSH (optional but recommended)
sudo nano /etc/ssh/sshd_config
# Set: PermitRootLogin no
# Set: PasswordAuthentication no (after setting up SSH keys)
sudo systemctl restart sshd

# Keep API key secure
chmod 600 config/config_comprehensive.yaml

# Regular backups
# Add to crontab:
# 0 3 * * * tar -czf ~/backups/youtube_db_$(date +\%Y\%m\%d).tar.gz ~/youtube_monitoring_pipeline/data/youtube_monitoring.db
```

---

## Quick Reference Commands

```bash
# Start collection in screen
screen -S youtube && cd ~/youtube_monitoring_pipeline && source venv/bin/activate && python collect_comprehensive.py --sources data/sources.csv

# Monitor
./monitor.sh

# View stats
python view_data.py --stats

# Export data
./export_data.sh

# Download to local
scp youtube_collector@SERVER:~/youtube_monitoring_pipeline/exports_*.tar.gz .

# Resume after interruption
python collect_comprehensive.py --sources data/sources.csv --resume
```

---

## Next Steps

1. ✅ Setup server and upload project
2. ✅ Test with 10 channels
3. ✅ Start full comprehensive collection
4. ✅ Monitor daily
5. ✅ Export and analyze data

Ready to deploy? Let me know which cloud provider you're using!
