"""
National Price Forecast Service
Advanced location-free commodity price forecasting using Agmarknet API
Features: Improved data cleaning, better forecasting, seasonality adjustment
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import statistics
from collections import defaultdict

logger = logging.getLogger(__name__)


class NationalPriceForecastService:
    """
    National-level price forecasting service.
    Fetches all-India data and calculates national daily averages.
    """
    
    # Commodity name mappings for API
    COMMODITY_MAPPINGS = {
        'Wheat': 'Wheat',
        'Rice': 'Rice',
        'Paddy': 'Paddy(Dhan)(Common)',
        'Potato': 'Potato',
        'Onion': 'Onion',
        'Tomato': 'Tomato',
        'Maize': 'Maize',
        'Cotton': 'Cotton',
        'Sugarcane': 'Sugarcane',
        'Soybean': 'Soyabean',
        'Soyabean': 'Soyabean',
        'Groundnut': 'Groundnut',
        'Peanut': 'Groundnut',
        'Gram': 'Bengal Gram(Gram)(Whole)',
        'Bengal Gram': 'Bengal Gram(Gram)(Whole)',
        'Chickpea': 'Bengal Gram(Gram)(Whole)',
        'Tur': 'Tur (Arhar)(Whole)',
        'Arhar': 'Tur (Arhar)(Whole)',
        'Moong': 'Moong(Green Gram)(Whole)',
        'Green Gram': 'Moong(Green Gram)(Whole)',
        'Urad': 'Urad(Black Gram)(Whole)',
        'Black Gram': 'Urad(Black Gram)(Whole)',
        'Apple': 'Apple',
        'Banana': 'Banana',
        'Cabbage': 'Cabbage',
        'Brinjal': 'Brinjal',
        'Cauliflower': 'Cauliflower',
        'Carrot': 'Carrot',
    }
    
    def __init__(self):
        """Initialize the service with API configuration"""
        self.base_url = os.getenv(
            'AGMARKNET_BASE_URL',
            'https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070'
        )
        self.api_key = os.getenv('AGMARKNET_API_KEY', '')
        self.timeout = int(os.getenv('API_TIMEOUT_SECONDS', '15'))
        
        # Set up requests session with retry
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        logger.info(f"NationalPriceForecastService initialized")
    
    def normalize_commodity_name(self, commodity: str) -> str:
        """Normalize commodity name to match API format"""
        commodity = commodity.strip().title()
        return self.COMMODITY_MAPPINGS.get(commodity, commodity)
    
    def get_commodity_suggestions(self) -> List[str]:
        """Get list of supported commodities for auto-suggestions"""
        return sorted(list(self.COMMODITY_MAPPINGS.keys()))
    
    def fetch_national_data(self, commodity: str, days: int = 90) -> List[Dict[str, Any]]:
        """Fetch all-India data for a commodity (no location filter)"""
        normalized_commodity = self.normalize_commodity_name(commodity)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        logger.info(f"Fetching national data for {normalized_commodity} (last {days} days)")
        
        all_records = []
        offset = 0
        limit = 1000
        
        while True:
            params = {
                'api-key': self.api_key,
                'format': 'json',
                'limit': limit,
                'offset': offset,
                'filters[commodity]': normalized_commodity,
            }
            
            try:
                response = self.session.get(self.base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                data = response.json()
                
                records = data.get('records', [])
                if not records:
                    break
                
                # Parse and filter records
                for record in records:
                    arrival_date_str = record.get('arrival_date', '')
                    
                    try:
                        arrival_date = datetime.strptime(arrival_date_str, '%d/%m/%Y')
                        
                        if start_date <= arrival_date <= end_date:
                            modal_price = self._parse_price(record.get('modal_price'))
                            
                            if modal_price > 0:
                                all_records.append({
                                    'date': arrival_date.strftime('%Y-%m-%d'),
                                    'price': modal_price,
                                    'market': record.get('market', ''),
                                    'state': record.get('state', ''),
                                    'district': record.get('district', '')
                                })
                    except (ValueError, TypeError):
                        continue
                
                if len(records) < limit:
                    break
                
                offset += limit
                
                if offset > 10000:
                    logger.warning("Reached maximum offset limit (10000)")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"API request failed: {str(e)}")
                break
        
        logger.info(f"Fetched {len(all_records)} records from {len(set(r['market'] for r in all_records))} markets")
        return all_records
    
    def calculate_national_daily_averages(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Calculate national daily average prices with improved outlier handling.
        Uses median for robustness against extreme values.
        """
        if not records:
            return []
        
        # Group by date
        date_prices = defaultdict(list)
        for record in records:
            date = record['date']
            price = record['price']
            # Basic outlier filtering: reject prices that are too extreme
            if 0 < price < 1000000:  # Reasonable price range
                date_prices[date].append(price)
        
        # Calculate daily statistics with outlier removal
        daily_averages = []
        for date in sorted(date_prices.keys()):
            prices = date_prices[date]
            
            if not prices:
                continue
            
            # Remove outliers using IQR method if enough data points
            if len(prices) >= 10:
                prices_sorted = sorted(prices)
                q1_idx = len(prices_sorted) // 4
                q3_idx = 3 * len(prices_sorted) // 4
                q1 = prices_sorted[q1_idx]
                q3 = prices_sorted[q3_idx]
                iqr = q3 - q1
                
                # Filter outliers
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                filtered_prices = [p for p in prices if lower_bound <= p <= upper_bound]
                
                if filtered_prices:
                    prices = filtered_prices
            
            # Use median for central tendency (more robust than mean)
            median_price = statistics.median(prices)
            mean_price = statistics.mean(prices)
            
            daily_averages.append({
                'date': date,
                'price': round(median_price, 2),  # Use median as primary
                'mean_price': round(mean_price, 2),
                'min_price': round(min(prices), 2),
                'max_price': round(max(prices), 2),
                'num_markets': len(prices),
                'std_dev': round(statistics.stdev(prices), 2) if len(prices) > 1 else 0
            })
        
        # Fill missing dates with interpolation
        return self._fill_missing_dates(daily_averages)
    
    def _fill_missing_dates(self, daily_averages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fill missing dates with linear interpolation"""
        if len(daily_averages) < 2:
            return daily_averages
        
        filled_data = []
        for i in range(len(daily_averages) - 1):
            current = daily_averages[i]
            next_item = daily_averages[i + 1]
            
            filled_data.append(current)
            
            # Check for gap
            current_date = datetime.strptime(current['date'], '%Y-%m-%d')
            next_date = datetime.strptime(next_item['date'], '%Y-%m-%d')
            gap_days = (next_date - current_date).days
            
            # Fill gaps up to 3 days with interpolation
            if 1 < gap_days <= 3:
                price_step = (next_item['price'] - current['price']) / gap_days
                
                for day in range(1, gap_days):
                    fill_date = current_date + timedelta(days=day)
                    interpolated_price = current['price'] + (price_step * day)
                    
                    filled_data.append({
                        'date': fill_date.strftime('%Y-%m-%d'),
                        'price': round(interpolated_price, 2),
                        'mean_price': round(interpolated_price, 2),
                        'min_price': round(interpolated_price, 2),
                        'max_price': round(interpolated_price, 2),
                        'num_markets': 0,  # Interpolated
                        'std_dev': 0,
                        'interpolated': True
                    })
        
        # Add last item
        filled_data.append(daily_averages[-1])
        return filled_data
    
    def generate_forecast(self, daily_averages: List[Dict[str, Any]], days: int = 7) -> List[Dict[str, Any]]:
        """
        Enhanced price forecast with improved trend calculation and seasonality adjustment.
        Supports 7-30 day forecasts with smoother confidence bounds.
        """
        if len(daily_averages) < 7:
            logger.warning("Insufficient data for forecasting")
            return []
        
        # Validate forecast days
        days = max(7, min(days, 30))  # Clamp between 7 and 30
        
        # Use last 30-60 days for better trend estimation
        lookback_days = min(60, len(daily_averages))
        recent_data = daily_averages[-lookback_days:]
        prices = [d['price'] for d in recent_data]
        
        # Enhanced trend calculation using weighted linear regression
        n = len(prices)
        weights = [1 + (i / n) * 0.5 for i in range(n)]  # Recent data weighted more
        
        x_values = list(range(n))
        x_mean = sum(x * w for x, w in zip(x_values, weights)) / sum(weights)
        y_mean = sum(p * w for p, w in zip(prices, weights)) / sum(weights)
        
        numerator = sum(w * (x - x_mean) * (p - y_mean) 
                       for x, p, w in zip(x_values, prices, weights))
        denominator = sum(w * (x - x_mean) ** 2 
                         for x, w in zip(x_values, weights))
        
        trend = numerator / denominator if denominator != 0 else 0
        
        # Calculate seasonality factor (simple monthly pattern)
        seasonality_factor = self._calculate_seasonality(daily_averages)
        
        # Calculate volatility for confidence bounds
        recent_prices = prices[-14:]  # Last 2 weeks
        volatility = statistics.stdev(recent_prices) if len(recent_prices) > 1 else statistics.stdev(prices)
        
        # Generate forecast
        last_price = prices[-1]
        last_date = datetime.strptime(daily_averages[-1]['date'], '%Y-%m-%d')
        
        forecast = []
        
        for i in range(1, days + 1):
            forecast_date = last_date + timedelta(days=i)
            
            # Base forecast with trend
            base_forecast = last_price + (trend * i)
            
            # Apply seasonality adjustment (dampened for longer forecasts)
            seasonality_weight = max(0.3, 1 - (i / days) * 0.5)
            adjusted_forecast = base_forecast * (1 + seasonality_factor * seasonality_weight)
            
            # Smoother confidence bounds that widen gradually
            # Use square root for smoother growth
            confidence_multiplier = 1 + (i ** 0.7) * 0.08
            confidence_margin = volatility * confidence_multiplier
            
            forecast.append({
                'date': forecast_date.strftime('%Y-%m-%d'),
                'predicted_price': round(max(adjusted_forecast, 0), 2),
                'lower_bound': round(max(adjusted_forecast - confidence_margin, 0), 2),
                'upper_bound': round(adjusted_forecast + confidence_margin, 2),
                'confidence': round(max(50, 90 - i * 1.5), 1)  # Decreasing confidence
            })
        
        return forecast
    
    def _calculate_seasonality(self, daily_averages: List[Dict[str, Any]]) -> float:
        """
        Calculate simple seasonality factor based on recent price patterns.
        Returns a factor between -0.1 and 0.1 representing seasonal trend.
        """
        if len(daily_averages) < 30:
            return 0.0
        
        try:
            # Compare recent 7 days vs previous 7 days
            recent_7 = [d['price'] for d in daily_averages[-7:]]
            previous_7 = [d['price'] for d in daily_averages[-14:-7]]
            
            recent_avg = statistics.mean(recent_7)
            previous_avg = statistics.mean(previous_7)
            
            # Calculate percentage change
            if previous_avg > 0:
                change = (recent_avg - previous_avg) / previous_avg
                # Clamp to reasonable range
                return max(-0.1, min(0.1, change * 0.3))
            
        except (ValueError, ZeroDivisionError):
            pass
        
        return 0.0
    
    def calculate_market_insights(self, daily_averages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Enhanced market insights with better trend detection and volatility analysis.
        Provides more accurate recommendations based on multiple factors.
        """
        if len(daily_averages) < 7:
            # Provide more helpful feedback based on available data
            days_available = len(daily_averages)
            current_price = daily_averages[-1]['price'] if daily_averages else 0
            
            if days_available == 0:
                message = '❌ No recent market data available for this commodity. Try popular commodities like Wheat, Rice, Onion, or Tomato.'
            elif days_available < 3:
                message = f'⚠️ Only {days_available} day(s) of data available. Need at least 7 days for accurate forecasting. Check back in a few days or try a different commodity.'
            else:
                # Show limited insights for 3-6 days
                recent_trend = 'stable'
                if days_available >= 2:
                    price_change = ((daily_averages[-1]['price'] - daily_averages[0]['price']) / daily_averages[0]['price'] * 100)
                    if price_change > 3:
                        recent_trend = 'increasing'
                    elif price_change < -3:
                        recent_trend = 'decreasing'
                
                message = f'📊 Limited data ({days_available} days). Current price: ₹{current_price:.2f}. Recent trend: {recent_trend}. Full forecast requires 7+ days of data.'
            
            return {
                'trend': 'insufficient_data',
                'volatility': 'unknown',
                'price_change_7d': 0.0,
                'price_change_30d': 0.0,
                'price_change_60d': 0.0,
                'recommendation': message,
                'current_price': current_price,
                'avg_price_30d': current_price,
                'momentum': 'neutral',
                'days_available': days_available
            }
        
        recent_7d = daily_averages[-7:]
        recent_30d = daily_averages[-30:] if len(daily_averages) >= 30 else daily_averages
        recent_60d = daily_averages[-60:] if len(daily_averages) >= 60 else daily_averages
        
        prices_7d = [d['price'] for d in recent_7d]
        prices_30d = [d['price'] for d in recent_30d]
        prices_60d = [d['price'] for d in recent_60d]
        
        # Enhanced trend calculation with momentum
        price_change_7d = ((prices_7d[-1] - prices_7d[0]) / prices_7d[0] * 100) if prices_7d[0] > 0 else 0
        price_change_30d = ((prices_30d[-1] - prices_30d[0]) / prices_30d[0] * 100) if prices_30d[0] > 0 else 0
        price_change_60d = ((prices_60d[-1] - prices_60d[0]) / prices_60d[0] * 100) if len(prices_60d) >= 60 and prices_60d[0] > 0 else 0
        
        # Determine trend with more nuanced thresholds
        if price_change_7d > 5:
            trend = 'strongly_increasing'
        elif price_change_7d > 2:
            trend = 'increasing'
        elif price_change_7d < -5:
            trend = 'strongly_decreasing'
        elif price_change_7d < -2:
            trend = 'decreasing'
        else:
            trend = 'stable'
        
        # Calculate momentum (comparing short-term vs long-term trends)
        if abs(price_change_7d) > abs(price_change_30d) * 0.5:
            momentum = 'accelerating' if price_change_7d * price_change_30d > 0 else 'reversing'
        else:
            momentum = 'steady'
        
        # Enhanced volatility calculation
        std_dev_7d = statistics.stdev(prices_7d) if len(prices_7d) > 1 else 0
        std_dev_30d = statistics.stdev(prices_30d) if len(prices_30d) > 1 else 0
        mean_price = statistics.mean(prices_30d)
        
        # Coefficient of variation
        cv = (std_dev_30d / mean_price) if mean_price > 0 else 0
        
        # Recent volatility vs historical
        volatility_ratio = (std_dev_7d / std_dev_30d) if std_dev_30d > 0 else 1
        
        if cv < 0.03:
            volatility = 'very_low'
        elif cv < 0.08:
            volatility = 'low'
        elif cv < 0.15:
            volatility = 'medium'
        elif cv < 0.25:
            volatility = 'high'
        else:
            volatility = 'very_high'
        
        # Enhanced recommendation engine
        recommendation = self._generate_smart_recommendation(
            trend, volatility, momentum, price_change_7d, price_change_30d, volatility_ratio
        )
        
        return {
            'trend': trend,
            'volatility': volatility,
            'momentum': momentum,
            'price_change_7d': round(price_change_7d, 1),
            'price_change_30d': round(price_change_30d, 1),
            'price_change_60d': round(price_change_60d, 1),
            'recommendation': recommendation,
            'current_price': prices_7d[-1],
            'avg_price_30d': round(mean_price, 2),
            'volatility_ratio': round(volatility_ratio, 2)
        }
    
    def _generate_smart_recommendation(self, trend: str, volatility: str, momentum: str, 
                                       change_7d: float, change_30d: float, vol_ratio: float) -> str:
        """Generate intelligent recommendation based on multiple market factors"""
        
        # Strong uptrend scenarios
        if trend in ['strongly_increasing', 'increasing']:
            if momentum == 'accelerating':
                return f"🚀 Strong upward momentum (+{change_7d:.1f}% in 7 days). Prices likely to rise further. Consider holding for 7-14 days for better returns."
            elif volatility in ['low', 'very_low']:
                return f"📈 Steady price increase (+{change_7d:.1f}% in 7 days) with low volatility. Good time to hold and sell in coming weeks."
            elif volatility in ['high', 'very_high']:
                return f"⚠️ Prices rising but highly volatile. Consider selling at current peak or wait for stabilization."
            else:
                return f"📈 Prices trending upward (+{change_7d:.1f}% in 7 days). Monitor daily and sell when you see price plateau."
        
        # Strong downtrend scenarios
        elif trend in ['strongly_decreasing', 'decreasing']:
            if momentum == 'accelerating':
                return f"🔴 Rapid price decline ({change_7d:.1f}% in 7 days). Sell immediately to minimize losses."
            elif volatility in ['high', 'very_high']:
                return f"⚠️ Falling prices with high volatility. Very risky market. Sell soon or wait for reversal signal."
            else:
                return f"📉 Prices declining ({change_7d:.1f}% in 7 days). Consider selling soon before further drops."
        
        # Stable market scenarios
        elif trend == 'stable':
            if volatility in ['very_low', 'low']:
                return f"✅ Market is stable with low volatility. Excellent time to sell at predictable prices."
            elif volatility in ['high', 'very_high']:
                return f"⚡ Stable trend but high volatility. Wait for clearer market direction before selling."
            else:
                return f"📊 Market stable ({change_7d:+.1f}% in 7 days). Good time to sell at current rates."
        
        # Momentum reversal scenarios
        if momentum == 'reversing':
            if change_7d > 0 and change_30d < 0:
                return f"🔄 Market reversing upward after decline. Potential recovery - consider holding short-term."
            elif change_7d < 0 and change_30d > 0:
                return f"🔄 Uptrend reversing downward. Sell now before prices drop further."
        
        # Default recommendation
        return f"📊 Market showing mixed signals. Current change: {change_7d:+.1f}% (7d). Verify with local mandi before deciding."
    
    def get_national_forecast(self, commodity: str, forecast_days: int = 7) -> Dict[str, Any]:
        """Main method to get complete national forecast"""
        try:
            # Fetch all-India data
            all_records = self.fetch_national_data(commodity, days=90)
            
            if not all_records:
                # Suggest popular alternatives
                popular_commodities = ['Wheat', 'Rice', 'Onion', 'Tomato', 'Potato', 'Maize']
                suggestions = ', '.join(popular_commodities)
                
                return {
                    'success': False,
                    'error': f'No data available for {commodity}. Please check the commodity name and try again.',
                    'suggestions': popular_commodities,
                    'help_text': f'Try these popular commodities with reliable data: {suggestions}'
                }
            
            # Calculate national daily averages
            daily_averages = self.calculate_national_daily_averages(all_records)
            
            if not daily_averages:
                return {
                    'success': False,
                    'error': 'Unable to calculate national averages from the available data'
                }
            
            # Check data freshness
            last_data_date = datetime.strptime(daily_averages[-1]['date'], '%Y-%m-%d')
            days_since_update = (datetime.now() - last_data_date).days
            
            data_freshness = 'fresh' if days_since_update <= 2 else 'stale' if days_since_update <= 7 else 'outdated'
            
            logger.info(f"Calculated {len(daily_averages)} daily averages (last update: {days_since_update} days ago)")
            
            # Generate forecast
            forecast = self.generate_forecast(daily_averages, days=forecast_days)
            
            # Calculate insights
            insights = self.calculate_market_insights(daily_averages)
            
            # Calculate confidence score based on data availability
            confidence_score = min(85, 60 + (len(daily_averages) / 90 * 25))
            
            # Build response
            return {
                'success': True,
                'commodity': self.normalize_commodity_name(commodity),
                'data_points': len(all_records),
                'markets_covered': len(set(r['market'] for r in all_records)),
                'states_covered': len(set(r['state'] for r in all_records)),
                'current_national_avg': daily_averages[-1]['price'] if daily_averages else 0,
                'historical_data': daily_averages[-30:],  # Last 30 days
                'forecast': forecast,
                'market_insights': insights,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'last_data_date': daily_averages[-1]['date'],
                'data_freshness': data_freshness,
                'days_since_update': days_since_update,
                'source': 'Agmarknet (data.gov.in)',
                'confidence_score': round(confidence_score, 1)
            }
            
        except Exception as e:
            logger.error(f"Error generating forecast: {str(e)}", exc_info=True)
            return {
                'success': False,
                'error': f'Error generating forecast: {str(e)}'
            }
    
    def _parse_price(self, price_str: Any) -> float:
        """Parse price string to float"""
        if price_str is None or price_str == '':
            return 0.0
        
        try:
            if isinstance(price_str, str):
                price_str = price_str.replace(',', '').strip()
            return float(price_str)
        except (ValueError, TypeError):
            return 0.0
