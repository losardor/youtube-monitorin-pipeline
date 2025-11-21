# Setup Instructions

## Initial Setup

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd youtube_monitoring_pipeline
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure API Keys

**IMPORTANT:** Never commit your actual API keys to git!

Copy the template config files and add your YouTube API key:

```bash
# For basic collection
cp config/config.yaml.template config/config.yaml

# For comprehensive collection
cp config/config_comprehensive.yaml.template config/config_comprehensive.yaml
```

Then edit the config file(s) and replace `YOUR_YOUTUBE_API_KEY_HERE` with your actual API key.

**Get a YouTube API key:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project or select an existing one
3. Enable YouTube Data API v3
4. Create credentials (API key)
5. Copy the API key to your config file

### 5. Create Required Directories
```bash
mkdir -p data/raw data/processed data/checkpoints logs
```

### 6. Prepare Input Data

Create or copy your source CSV file to `data/sources.csv`. The file should have at least a `Youtube` column with channel URLs.

Example format:
```csv
Domain,Brand Name,Youtube,Rating,Orientation
example.com,Example News,https://www.youtube.com/@examplenews,T,Center
```

## Testing

Test your API key:
```bash
python test_api_quick.py
```

Test collection with a few channels:
```bash
python collect_comprehensive_fixed.py --sources data/sources.csv --max-channels 3
```

## Security Notes

The following files are excluded from git (via `.gitignore`):
- `config/config.yaml` - Contains your API key
- `config/config_comprehensive.yaml` - Contains your API key
- `data/youtube_monitoring.db` - Large database file
- `data/sources.csv` - May contain proprietary data
- `logs/*.log` - Log files
- `venv/` - Virtual environment

**Never commit these files to version control!**

## Usage

See README.md for detailed usage instructions.
