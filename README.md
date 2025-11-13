# FarmLink AI 🌾

A comprehensive agricultural marketplace platform powered by AI, connecting farmers with buyers while providing intelligent crop management, pest detection, weather forecasting, and logistics solutions.

## 🚀 Features

### Core Marketplace
- **User Management**: Multi-role system (Farmers, Buyers, Admins, Experts)
- **Crop Listings**: Create, manage, and browse agricultural products
- **Order Management**: Complete order lifecycle from placement to delivery
- **Payment Integration**: Secure payments via Razorpay
- **Rating & Review System**: Build trust through transparent feedback

### AI-Powered Services
- **Crop Disease Detection**: AI-based pest and disease identification
- **Weather Forecasting**: Real-time weather data and predictions
- **Price Forecasting**: Market price predictions using historical data
- **Crop Recommendations**: Personalized suggestions based on conditions
- **AI Chat Assistant**: Gemini-powered agricultural advisory

### Advanced Features
- **Expert Forum**: Community-driven Q&A platform with moderation
- **Learning Hub**: Educational articles and resources for farmers
- **Achievement System**: Gamification to encourage platform engagement
- **Shipment Tracking**: Real-time order tracking with multiple courier integrations
- **KYC Verification**: Secure identity verification with encrypted document storage
- **Fraud Prevention**: Multi-layered security with rate limiting and anomaly detection
- **Analytics Dashboard**: Comprehensive insights for admins and users

### Security & Compliance
- **Two-Factor Authentication (2FA)**: Enhanced account security
- **End-to-End Encryption**: Secure data storage and transmission
- **CSRF Protection**: Built-in security against cross-site attacks
- **Role-Based Access Control**: Granular permission management
- **Audit Logging**: Complete activity tracking for compliance

## 🛠️ Technology Stack

### Backend
- **Framework**: Flask (Python)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: Flask-Login with 2FA support
- **Task Scheduling**: APScheduler for background jobs
- **Real-time**: Flask-SocketIO for live updates

### AI & Machine Learning
- **Google Gemini AI**: Natural language processing and recommendations
- **Custom ML Models**: Price forecasting and crop analysis

### External Integrations
- **Payment**: Razorpay
- **Email**: SMTP (Gmail/Custom)
- **SMS**: Twilio
- **Shipping**: Shiprocket, India Post
- **Weather**: Weather API integration
- **Government Data**: Data.gov.in, eNAM APIs

### Security & Storage
- **Encryption**: Cryptography (Fernet)
- **File Security**: ClamAV virus scanning
- **Session Management**: Custom secure session handling

## 📋 Prerequisites

- Python 3.8+
- PostgreSQL 12+
- pip (Python package manager)
- Virtual environment (recommended)

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone <repository-url>
cd farmlink-ai
```

### 2. Create Virtual Environment
```bash
python -m venv .venv
```

### 3. Activate Virtual Environment
**Windows:**
```bash
.venv\Scripts\activate
```

**Linux/Mac:**
```bash
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment Variables
```bash
cp .env.example .env
```

Edit `.env` and fill in your configuration values:
- Database credentials
- API keys (Gemini, OpenAI, Weather, etc.)
- Email SMTP settings
- Payment gateway credentials
- Encryption keys
- Courier service credentials

### 6. Initialize Database
```bash
python
>>> from app import app, db
>>> with app.app_context():
>>>     db.create_all()
>>> exit()
```

### 7. (Optional) Seed Learning Articles
```bash
python seed_learning_articles.py
```

## 🚀 Running the Application

### Development Mode
```bash
python app.py
```

The application will be available at `http://localhost:5000`

### Production Mode (Gunicorn)
```bash
gunicorn --bind 0.0.0.0:5000 app:app
```

## 📁 Project Structure

```
farmlink-ai/
├── app.py                          # Main application entry point
├── models.py                       # Database models
├── routes.py                       # Core application routes
├── config.py                       # Configuration management
├── extensions.py                   # Flask extensions initialization
│
├── AI Services/
│   ├── ai_services.py             # General AI utilities
│   ├── crop_ai_service.py         # Crop-specific AI features
│   ├── pest_detection_service.py  # Disease detection
│   └── learning_recommendation_service.py
│
├── Business Logic/
│   ├── order_service.py           # Order processing
│   ├── payment_service.py         # Payment handling
│   ├── rating_service.py          # Rating system
│   ├── kyc_service.py             # KYC verification
│   ├── achievement_service.py     # Gamification
│   └── analytics_service.py       # Analytics engine
│
├── Security/
│   ├── encryption_service.py      # Data encryption
│   ├── encryption_utils.py        # Encryption helpers
│   ├── security_utils.py          # Security utilities
│   ├── fraud_prevention_service.py # Fraud detection
│   └── kyc_security.py            # KYC security
│
├── Tracking & Logistics/
│   ├── tracking_service.py        # Shipment tracking
│   ├── tracking_routes.py         # Tracking endpoints
│   ├── tracking_scheduler.py      # Background jobs
│   ├── tracking_webhooks.py       # Webhook handlers
│   └── courier_adapters.py        # Courier integrations
│
├── Admin/
│   ├── admin_crop_routes.py       # Crop management
│   ├── admin_order_routes.py      # Order management
│   ├── admin_analytics_routes.py  # Analytics dashboard
│   ├── admin_security_routes.py   # Security controls
│   └── admin_shipment_routes.py   # Shipment management
│
├── Communication/
│   ├── email_service.py           # Email notifications
│   ├── rating_notification_service.py
│   └── tracking_notifications.py  # Tracking alerts
│
├── API/
│   ├── api_routes.py              # REST API endpoints
│   └── api_utils.py               # API utilities
│
├── Templates & Static/
│   ├── templates/                 # HTML templates
│   └── static/                    # CSS, JS, images
│
└── Configuration/
    ├── .env                       # Environment variables
    ├── requirements.txt           # Python dependencies
    ├── Procfile                   # Deployment config
    └── render.yaml                # Render deployment
```

## 🔑 Key Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `SESSION_SECRET` | Flask session secret key | Yes |
| `GEMINI_API_KEY` | Google Gemini AI API key | Yes |
| `RAZORPAY_KEY_ID` | Razorpay payment key | Yes |
| `RAZORPAY_KEY_SECRET` | Razorpay secret | Yes |
| `MAIL_USERNAME` | SMTP email username | Yes |
| `MAIL_PASSWORD` | SMTP email password | Yes |
| `ENCRYPTION_KEY` | Fernet encryption key | Yes |
| `KYC_ENCRYPTION_KEY` | KYC data encryption key | Yes |
| `WEATHER_API_KEY` | Weather service API key | No |
| `TWILIO_ACCOUNT_SID` | Twilio SMS account SID | No |
| `SHIPROCKET_EMAIL` | Shiprocket account email | No |

## 🎯 User Roles

### Farmer
- List crops for sale
- Manage inventory
- Track orders and shipments
- Access AI-powered recommendations
- Participate in expert forum
- Complete KYC verification

### Buyer
- Browse and purchase crops
- Track orders
- Rate and review transactions
- Access market insights
- Communicate with farmers

### Expert
- Answer farmer questions
- Provide agricultural guidance
- Moderate forum content
- Share knowledge articles

### Admin
- Manage users and roles
- Monitor platform activity
- Access analytics dashboard
- Configure system settings
- Handle disputes and moderation

## 📊 API Endpoints

### Public APIs
- `GET /api/crops` - List available crops
- `GET /api/crops/<id>` - Get crop details
- `GET /api/weather` - Weather information

### Authenticated APIs
- `POST /api/orders` - Create order
- `GET /api/orders/<id>` - Order details
- `POST /api/ratings` - Submit rating
- `GET /api/tracking/<tracking_id>` - Track shipment

### Admin APIs
- `GET /api/admin/analytics` - Platform analytics
- `GET /api/admin/users` - User management
- `POST /api/admin/moderate` - Content moderation

## 🔒 Security Features

1. **Authentication & Authorization**
   - Secure password hashing (Werkzeug)
   - Two-factor authentication (TOTP)
   - Role-based access control
   - Session management with secure cookies

2. **Data Protection**
   - End-to-end encryption for sensitive data
   - Encrypted KYC document storage
   - CSRF protection on all forms
   - SQL injection prevention (SQLAlchemy ORM)

3. **Fraud Prevention**
   - Rate limiting on sensitive endpoints
   - Anomaly detection for suspicious activities
   - IP-based access controls
   - Transaction monitoring

4. **Compliance**
   - Audit logging for all critical operations
   - GDPR-compliant data handling
   - Secure file upload with virus scanning
   - PII encryption at rest

## 🧪 Testing

```bash
# Run tests (if test suite is available)
pytest

# Check code quality
flake8 .

# Security audit
pip-audit
```

## 📦 Deployment

### Render.com (Recommended)
1. Connect your GitHub repository
2. Configure environment variables in Render dashboard
3. Deploy using `render.yaml` configuration
4. Database will be provisioned automatically

### Manual Deployment
1. Set up PostgreSQL database
2. Configure environment variables
3. Run database migrations
4. Start application with Gunicorn
5. Set up reverse proxy (Nginx recommended)
6. Configure SSL certificates

## 🔄 Background Jobs

The application runs several scheduled tasks:
- **Shipment Tracking Updates**: Every 4 hours
- **Price Forecast Updates**: Daily
- **Email Notifications**: Real-time
- **Analytics Aggregation**: Hourly
- **Cache Cleanup**: Daily

## 📝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 🐛 Troubleshooting

### Database Connection Issues
- Verify PostgreSQL is running
- Check DATABASE_URL format
- Ensure database exists and user has permissions

### Email Not Sending
- Verify SMTP credentials
- Check firewall/port settings
- Enable "Less secure app access" for Gmail (or use App Password)

### AI Services Not Working
- Verify API keys are correct
- Check API rate limits
- Review logs for specific errors

### Payment Integration Issues
- Confirm Razorpay credentials
- Check webhook configuration
- Verify test/live mode settings

## 📄 License

[Specify your license here]

## 👥 Support

For issues and questions:
- Create an issue on GitHub
- Contact: [your-email]
- Documentation: [link-to-docs]

## 🙏 Acknowledgments

- Google Gemini AI for intelligent recommendations
- Razorpay for payment processing
- Open-source community for amazing tools

---

**Built with ❤️ for the farming community**
