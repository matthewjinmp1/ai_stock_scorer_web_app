# AI Stock Scorer

An intelligent competitive moat analysis tool powered by xAI's Grok that evaluates companies across 8 key competitive advantage metrics. Uses AI to provide quantitative competitive moat scoring for any company.

## Overview

This tool uses Grok LLM to analyze companies and provides competitive moat scores across 8 dimensions:
- **Competitive Moat** (0-10): Overall competitive advantage strength
- **Barriers to Entry** (0-10): Difficulty for new competitors to enter the market
- **Disruption Risk** (0-10): Vulnerability to technological disruption
- **Switching Cost** (0-10): Cost for customers to switch to competitors
- **Brand Strength** (0-10): Brand recognition, loyalty, and premium pricing ability
- **Competition Intensity** (0-10): Aggressiveness and number of competitors
- **Network Effect** (0-10): Value increase with more users/customers
- **Product Differentiation** (0-10): Product uniqueness and pricing power

All scores are persisted in `scores.json` to avoid redundant API calls.

## Features

- **AI-Powered Analysis**: Uses Grok-4 to evaluate companies across competitive metrics
- **Persistent Storage**: Saves all scores to avoid duplicate queries
- **Interactive Mode**: Enter company names to get instant moat analysis
- **Credit Management**: Built-in tool to check API credit availability
- **Comprehensive Scoring**: 7-dimensional analysis of competitive positioning
- **Fast & Efficient**: Uses `grok-4-fast` model for quick responses

## Prerequisites

- Python 3.7 or higher
- xAI API key (get one from [https://console.x.ai/](https://console.x.ai/))

## Installation

1. Clone this repository:
```bash
git clone https://github.com/matthewjinmp1/AI_stock_scorer.git
cd AI_stock_scorer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Copy the config template and add your API key:
```bash
cp config_template.py config.py
```

4. Edit `config.py` and add your xAI API key:
```python
XAI_API_KEY = "your_api_key_here"
```

**Note**: `config.py` is already in `.gitignore` to protect your API key.

## Usage

### Main Application: Company Moat Scorer

Run the main scoring application:

```bash
python scorer.py
```

Then enter ticker symbols or company names when prompted. The tool will:
- Check if the company has been scored before
- Query Grok for missing scores
- Display all 8 metrics (0-10 scale)
- Save scores to `scores.json`

**Example interaction:**
```
Enter ticker or company name (or 'view'/'fill'/'quit'): TSLA
Analyzing TSLA...
Querying Competitive Moat...
Competitive Moat Score: 8/10
Querying Barriers to Entry...
Barriers to Entry Score: 9/10
...
```

### Check API Credits

Monitor your xAI API credit availability:

```bash
python check_credits.py
```

This will attempt API calls to verify credits are available.

### Basic Examples

Try example queries to the Grok API:

```bash
python examples.py
```

## Project Structure

- `scorer.py` - Main application for company competitive analysis
- `grok_client.py` - Grok API client wrapper
- `check_credits.py` - Tool to verify API credit availability
- `examples.py` - Basic usage examples
- `scores.json` - Persistent storage of all company scores
- `stock_tickers_clean.json` - Ticker symbol database
- `config.py` - Your API key (not in repo, see config_template.py)
- `config_template.py` - Template for configuration

## Competitive Moat Scoring Details

### What are Competitive Moats?

A competitive moat refers to a company's sustainable competitive advantages that protect it from competitors. This tool evaluates:

1. **Competitive Moat** - Overall strength across all dimensions
2. **Barriers to Entry** - Regulatory, capital, or technological hurdles
3. **Disruption Risk** - Vulnerability to new technologies or business models
4. **Switching Cost** - Lock-in effects (vendor switching, retraining, data migration)
5. **Brand Strength** - Customer loyalty, recognition, and pricing power
6. **Competition Intensity** - Market competition level and aggressiveness
7. **Network Effect** - Platform, marketplace, or ecosystem benefits
8. **Product Differentiation** - Product uniqueness vs commoditization

### Interpreting Scores

- **0-3**: Weak competitive position
- **4-6**: Moderate competitive position
- **7-8**: Strong competitive position
- **9-10**: Exceptional competitive position (rare)

## API Usage & Costs

This tool uses xAI's Grok API. Each company analysis requires multiple API calls (one per metric), so:
- Use credit checking script to monitor availability
- Consider costs when analyzing many companies
- Scores are cached to avoid duplicate API calls

## Example Scores

Sample scores from `scores.json`:

```json
{
  "companies": {
    "TSLA": {
      "moat_score": "8",
      "barriers_score": "9",
      "disruption_risk": "7",
      "switching_cost": "6",
      "brand_strength": "9",
      "competition_intensity": "8",
      "network_effect": "8"
    },
    "MSFT": {
      "moat_score": "9",
      "barriers_score": "9",
      "disruption_risk": "5",
      "switching_cost": "8",
      "brand_strength": "9",
      "competition_intensity": "8",
      "network_effect": "9"
    }
  }
}
```

## Troubleshooting

### "API key is required" error
1. Check that `config.py` exists
2. Verify your API key is set correctly
3. Ensure you have API credits available at https://console.x.ai/

### Company scores not updating
- Try deleting the company entry from `scores.json`
- Or manually edit the JSON to remove specific score fields

### API Rate Limiting
- Wait between queries if you hit rate limits
- The tool uses `grok-4-fast` for speed and cost efficiency

## Contributing

Contributions welcome! Areas for improvement:
- Additional scoring dimensions
- Historical score tracking
- Batch analysis of multiple companies
- Export to CSV/Excel
- Web interface

## License

MIT License - See LICENSE file for details.

## Support

For issues or questions:
- Open an issue on GitHub
- For xAI API issues, see [xAI documentation](https://docs.x.ai/)
