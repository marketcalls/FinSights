# FinSights

A minimalistic news summary platform for Indian stock market traders and investors. Built with FastAPI and powered by Perplexity AI.

## Features

- **Market Summaries**: Daily pre-market and post-market AI-generated summaries
- **Sector News**: Coverage of Banking, IT, Pharma, Auto, Energy, and more
- **Stock-Specific Search**: Search news by NSE/BSE stock symbols
- **Admin Panel**: Full control over news, scheduler, and settings
- **Scheduled Fetching**: Automated news collection via APScheduler
- **Cache-First Architecture**: Fast page loads with in-memory caching

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, SQLite
- **Frontend**: Jinja2, Tailwind CSS, DaisyUI
- **AI**: Perplexity API (Sonar model)
- **Scheduler**: APScheduler

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/finsights.git
cd finsights
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install frontend dependencies and build CSS:
```bash
npm install
npm run build:css
```

5. Run the application:
```bash
uvicorn app.main:app --reload
```

6. Open your browser:
- Public site: http://localhost:8000
- Admin panel: http://localhost:8000/admin

## Configuration

### Environment Variables

Create a `.env` file (optional):
```
SECRET_KEY=your-secret-key-here
```

### Admin Setup

Default admin credentials are created on first run:
- Username: `admin`
- Password: `admin123`

Change the password immediately after first login.

### Perplexity API Key

1. Get an API key from [perplexity.ai/settings/api](https://www.perplexity.ai/settings/api)
2. Go to Admin > Settings
3. Enter and validate your API key

## Project Structure

```
FinSights/
├── app/
│   ├── models/          # SQLAlchemy models
│   ├── routers/         # FastAPI routes
│   ├── services/        # Business logic
│   ├── templates/       # Jinja2 templates
│   ├── static/          # CSS, JS, images
│   ├── config.py        # Configuration
│   ├── database.py      # Database setup
│   └── main.py          # Application entry
├── symbols.csv          # Stock symbols list
├── requirements.txt     # Python dependencies
├── package.json         # Node dependencies
└── tailwind.config.js   # Tailwind configuration
```

## News Categories

| Category | Description |
|----------|-------------|
| Market | Pre-market, post-market summaries |
| Sectors | Banking, IT, Pharma, Auto, Energy, FMCG, Metals, Realty, Infra |
| Economy | GDP, inflation, RBI policy, government announcements |
| Global | US markets, Fed, China, crude oil, global events |
| IPO | Upcoming IPOs, listings, GMP |

## Scheduler Jobs

Jobs run automatically in IST timezone:
- **Pre-market summary**: 7:00 AM
- **Post-market summary**: 4:00 PM
- **Sector updates**: Every 2 hours during market hours
- **Economy news**: 8:00 AM
- **Global markets**: 6:00 AM

## API Endpoints

### Public
- `GET /` - Home page with all news
- `GET /category/{category}` - News by category
- `GET /search?q=SYMBOL` - Search by stock symbol

### Admin
- `GET /admin/dashboard` - Admin dashboard
- `GET /admin/news` - News management
- `GET /admin/scheduler` - Scheduler control
- `GET /admin/settings` - API key and settings
- `GET /admin/logs` - API call logs
- `GET /admin/users` - User management

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Disclaimer

This application is for informational purposes only. It does not constitute financial advice. Always do your own research before making investment decisions.
