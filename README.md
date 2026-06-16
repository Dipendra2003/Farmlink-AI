# FarmLink AI 🌾

**Connecting Farmers and Buyers with AI-Powered Agricultural Solutions**

FarmLink AI is a comprehensive agricultural marketplace platform that bridges the gap between farmers and buyers, powered by artificial intelligence and modern web technologies.

---

## 🚀 Features

### Core Marketplace
- **Direct Farm-to-Buyer Trading**: Connect farmers directly with buyers, eliminating middlemen
- **Real-time Inventory Management**: Track crop availability and stock levels
- **Smart Search & Filtering**: Find crops by category, location, price range, and more
- **Secure Payment Integration**: Razorpay payment gateway for safe transactions
- **Order Tracking**: Real-time shipment tracking with multiple courier integrations

### AI-Powered Features
- **Crop Recommendations**: AI-driven crop suggestions based on soil, climate, and market demand
- **Price Forecasting**: National-level commodity price predictions using Agmarknet data
- **Pest & Disease Detection**: Image-based analysis for early pest/disease identification
- **Weather Integration**: Real-time weather data for farming decisions

### Community & Learning
- **Expert Forum**: Q&A platform for agricultural experts and farmers
- **Learning Hub**: Educational articles on modern farming techniques
- **Rating & Review System**: Build trust through verified buyer-seller ratings
- **Achievement System**: Gamification to encourage platform engagement

### Security & Compliance
- **KYC Verification**: Secure seller verification with encrypted document storage
- **Role-Based Access Control**: Admin, Farmer, and Buyer roles with specific permissions
- **Fraud Prevention**: Rate limiting, IP tracking, and suspicious activity detection
- **Data Encryption**: End-to-end encryption for sensitive information

---

## 🛠️ Technology Stack

### Backend
- **Framework**: Flask (Python 3.11)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Authentication**: Flask-Login with secure session management
- **Email**: Flask-Mail with SMTP support
- **Task Scheduling**: APScheduler for background jobs

### Frontend
- **UI Framework**: Bootstrap 5
- **JavaScript**: Vanilla JS with modern ES6+ features
- **Icons**: Font Awesome
- **Image Processing**: Cropper.js for profile pictures

### AI & Data
- **AI Model**: Google Gemini API for intelligent recommendations
- **Price Data**: Agmarknet API (data.gov.in)
- **Weather API**: OpenWeatherMap integration
- **Data Analysis**: Pandas, NumPy, Statsmodels for forecasting

### Payment & Communication
- **Payment Gateway**: Razorpay
- **SMS Notifications**: Twilio
- **Shipment Tracking**: Shiprocket, India Post APIs

### Deployment
- **Web Server**: Gunicorn
- **Platform**: Render (recommended)
- **Database**: PostgreSQL (managed)
- **File Storage**: Local filesystem (upgradeable to S3)

---

## 📋 Prerequisites

- Python 3.11 or higher
- PostgreSQL 12 or higher
- pip (Python package manager)
- Git

---

## 🔧 Installation

### 1. Clone the Repository
```bash
git clone https://github.com/Dipendra2003/Farmlink-AI.git
cd Farmlink-AI
```

### 2. Create Virtual Environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Set Up Environment Variables
Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

**Required Environment Variables:**
```env
# Application
BASE_URL=http://localhost:5000
SESSION_SECRET=your-secret-key-here

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/farmlink_db

# AI APIs
GEMINI_API_KEY=your-gemini-api-key
WEATHER_API_KEY=your-weather-api-key
AGMARKNET_API_KEY=your-agmarknet-api-key

# Email (Gmail)
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com

# Payment
RAZORPAY_KEY_ID=your-razorpay-key-id
RAZORPAY_KEY_SECRET=your-razorpay-secret

# Encryption
KYC_ENCRYPTION_KEY=generate-using-fernet
ENCRYPTION_KEY=generate-using-fernet
```

**Generate Encryption Keys:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 5. Initialize Database
```bash
# The app will automatically create tables on first run
python main.py
```

### 6. Create Admin User
Access the application and register with role "admin" for the first user.

---

## 🚀 Running the Application

### Development Mode
```bash
python main.py
```
Access at: `http://localhost:5000`

### Production Mode (Gunicorn)
```bash
gunicorn main:app --workers 4 --bind 0.0.0.0:5000
```

---

## 🌐 Deployment to Render

### 1. Push to GitHub
```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

### 2. Create Render Account
- Sign up at [render.com](https://render.com)
- Connect your GitHub repository

### 3. Create PostgreSQL Database
- Go to Render Dashboard → New → PostgreSQL
- Name: `farmlink-db`
- Copy the Internal Database URL

### 4. Create Web Service
- Go to Render Dashboard → New → Web Service
- Connect your repository
- Configure:
  - **Name**: farmlink-ai
  - **Environment**: Python 3
  - **Build Command**: `pip install -r requirements.txt`
  - **Start Command**: `gunicorn app:app --workers 4 --timeout 120`

### 5. Set Environment Variables
Add all variables from `.env.example` in Render Dashboard:
- `BASE_URL`: Your Vercel URL (e.g., https://farmlinkai.vercel.app)
- `DATABASE_URL`: From PostgreSQL database (auto-filled)
- `SESSION_SECRET`: Generate random string
- All API keys and credentials

### 6. Deploy
Click "Create Web Service" and wait for deployment to complete.

---

## 📁 Project Structure

```
Farmlink-AI/
├── static/                 # Static files (CSS, JS, images)
│   ├── css/
│   ├── js/
│   ├── img/
│   └── uploads/           # User-uploaded files
├── templates/             # HTML templates
│   ├── admin/            # Admin dashboard
│   ├── ai/               # AI features
│   ├── auth/             # Authentication
│   ├── dashboard/        # User dashboards
│   ├── marketplace/      # Product listings
│   └── ...
├── app.py                # Flask application factory
├── main.py               # Application entry point
├── models.py             # Database models
├── routes.py             # Main routes
├── forms.py              # WTForms definitions
├── config.py             # Configuration
├── requirements.txt      # Python dependencies
├── Procfile             # Deployment configuration
├── render.yaml          # Render deployment config
└── .env.example         # Environment variables template
```

---

## 🔐 Security Features

- **Password Hashing**: Werkzeug secure password hashing
- **CSRF Protection**: Flask-WTF CSRF tokens
- **Session Security**: HTTPOnly, Secure, SameSite cookies
- **Rate Limiting**: Flask-Limiter for API endpoints
- **Input Sanitization**: Bleach for HTML sanitization
- **SQL Injection Prevention**: SQLAlchemy ORM
- **XSS Protection**: Template auto-escaping
- **File Upload Validation**: Type and size restrictions
- **KYC Encryption**: Fernet symmetric encryption

---

## 👥 User Roles

### Admin
- Full system access
- User management
- Crop approval/rejection
- Order management
- Analytics dashboard
- System settings

### Farmer
- List crops for sale
- Manage inventory
- Process orders
- View earnings
- Access AI tools
- KYC verification

### Buyer
- Browse marketplace
- Place orders
- Track shipments
- Rate products
- View purchase history
- Access learning resources

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 📧 Contact

**Developer**: Dipendra
**GitHub**: [@Dipendra2003](https://github.com/Dipendra2003)
**Repository**: [Farmlink-AI](https://github.com/Dipendra2003/Farmlink-AI)

---

## 🙏 Acknowledgments

- Google Gemini API for AI capabilities
- Agmarknet (data.gov.in) for agricultural data
- Razorpay for payment processing
- Render for hosting platform
- Bootstrap team for UI framework
- Flask community for excellent documentation

---

## 📊 API Documentation

### Public Endpoints
- `GET /api/crops` - List all available crops
- `GET /api/crop/<id>` - Get crop details
- `GET /api/crop/<id>/stock` - Check stock availability

### Authenticated Endpoints
- `POST /api/cart/add/<crop_id>` - Add to cart
- `POST /api/order/place` - Place order
- `GET /api/orders/my` - Get user orders
- `POST /api/rating/submit` - Submit rating

### Admin Endpoints
- `GET /api/admin/analytics` - System analytics
- `POST /api/admin/crop/approve/<id>` - Approve crop
- `GET /api/admin/users` - List users

---

## 🐛 Known Issues

- Large file uploads may timeout on free hosting tiers
- SMS notifications require Twilio credits
- Weather API has rate limits on free tier

---

## 🔮 Future Enhancements

- [ ] Mobile app (React Native)
- [ ] Multi-language support (Hindi, regional languages)
- [ ] Blockchain for supply chain tracking
- [ ] Advanced ML models for yield prediction
- [ ] Integration with government schemes
- [ ] Farmer insurance integration
- [ ] Cold storage facility finder
- [ ] Soil testing service integration

---

## 📈 Version History

### v1.0.0 (Current)
- Initial release
- Core marketplace functionality
- AI-powered features
- Payment integration
- Order tracking
- Community features

---

**Made with ❤️ for Indian Farmers**
