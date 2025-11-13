"""
Seed Learning Hub Articles
Creates 15 comprehensive articles for the FarmLink AI Learning Hub
Run: python seed_learning_articles.py
"""
from app import app, db
from models import LearningArticle, User
from datetime import datetime

def get_admin_user():
    """Get the admin user to be the author"""
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        print("Error: No admin user found. Please create an admin user first.")
        return None
    return admin

def create_articles(admin_id):
    """Create seed articles"""
    articles_data = [
        {
            'title': 'Complete Guide to Organic Farming for Beginners',
            'summary': 'Learn the fundamentals of organic farming, from soil preparation to pest management without chemicals.',
            'category': 'farming-basics',
            'difficulty_level': 'beginner',
            'reading_time': 8,
            'crop_type': 'general',
            'tags': 'organic, beginner, sustainable, soil-health',
            'content': '''# Complete Guide to Organic Farming for Beginners

## Introduction
Organic farming is a sustainable agricultural practice that focuses on growing crops without synthetic pesticides, fertilizers, or genetically modified organisms. This guide will help you start your organic farming journey.

## Key Principles of Organic Farming

### 1. Soil Health Management
- Build healthy soil through composting
- Use green manure and cover crops
- Maintain proper soil pH (6.0-7.0 for most crops)
- Practice crop rotation to prevent soil depletion

### 2. Natural Pest Control
- Encourage beneficial insects
- Use neem oil and organic pesticides
- Implement companion planting
- Practice proper crop spacing for air circulation

### 3. Water Management
- Use drip irrigation to conserve water
- Mulch to retain soil moisture
- Harvest rainwater when possible
- Water early morning or evening to reduce evaporation

## Getting Started

### Step 1: Soil Preparation
Start by testing your soil pH and nutrient levels. Add organic compost (2-3 inches) and work it into the top 6-8 inches of soil.

### Step 2: Choose Your Crops
Begin with easy-to-grow crops like tomatoes, lettuce, beans, and herbs. These are forgiving for beginners.

### Step 3: Create a Planting Schedule
Plan your planting based on your local climate and growing seasons.
'''
        },
        {
            'title': 'Advanced Drip Irrigation Systems: Installation and Maintenance',
            'summary': 'Master drip irrigation technology to save water and increase crop yields with this comprehensive guide.',
            'category': 'irrigation-techniques',
            'difficulty_level': 'intermediate',
            'reading_time': 12,
            'crop_type': 'general',
            'tags': 'irrigation, water-management, technology, efficiency',
            'content': '''# Advanced Drip Irrigation Systems

## Why Drip Irrigation?
Drip irrigation can save up to 60% water compared to traditional methods while increasing yields by 20-30%.

## System Components
1. **Water Source**: Well, tank, or municipal supply
2. **Pump**: Maintains consistent pressure (1.5-2.5 bar)
3. **Filters**: Remove particles that could clog emitters
4. **Main Line**: PVC pipes (25-50mm diameter)
5. **Lateral Lines**: PE pipes with emitters (12-16mm)
6. **Emitters**: Drip at 2-4 liters per hour

## Installation Steps
1. Design your layout based on crop spacing
2. Install main line along field length
3. Connect lateral lines perpendicular to main line
4. Place emitters near plant root zones
5. Install pressure regulator and filter
6. Test system for leaks and uniform flow

## Maintenance Schedule
- **Daily**: Check for leaks and clogged emitters
- **Weekly**: Clean filters
- **Monthly**: Flush system with clean water
- **Seasonally**: Replace damaged components
'''
        },
        {
            'title': 'Integrated Pest Management: A Sustainable Approach',
            'summary': 'Learn how to control pests effectively using IPM strategies that minimize chemical use and protect beneficial insects.',
            'category': 'pest-management',
            'difficulty_level': 'intermediate',
            'reading_time': 10,
            'crop_type': 'general',
            'tags': 'pest-control, IPM, sustainable, organic',
            'content': '''# Integrated Pest Management (IPM)

## What is IPM?
IPM is an ecosystem-based strategy that focuses on long-term prevention of pests through biological control, habitat manipulation, and resistant varieties.

## The Four-Tier Approach

### Tier 1: Prevention
- Select pest-resistant crop varieties
- Practice crop rotation
- Maintain field sanitation
- Use certified disease-free seeds

### Tier 2: Monitoring
- Scout fields regularly (2-3 times per week)
- Use pheromone traps for early detection
- Keep pest population records
- Identify beneficial insects

### Tier 3: Intervention Thresholds
- Determine economic threshold levels
- Act only when pest populations exceed thresholds
- Consider crop stage and market value

### Tier 4: Control Methods
**Biological Control:**
- Release predatory insects (ladybugs, lacewings)
- Use Bacillus thuringiensis (Bt) for caterpillars
- Encourage birds and bats

**Cultural Control:**
- Adjust planting dates to avoid peak pest periods
- Use trap crops to lure pests away
- Implement proper spacing for air circulation

**Chemical Control (Last Resort):**
- Use selective, low-toxicity pesticides
- Apply during pest-vulnerable life stages
- Rotate pesticide classes to prevent resistance
'''
        },
        {
            'title': 'Soil Health 101: Building Fertile Ground for Success',
            'summary': 'Understand soil composition, testing, and improvement techniques to create the perfect growing environment.',
            'category': 'soil-science',
            'difficulty_level': 'beginner',
            'reading_time': 7,
            'crop_type': 'general',
            'tags': 'soil-health, composting, nutrients, pH',
            'content': '''# Soil Health 101

## Understanding Soil Composition
Healthy soil contains:
- 45% Minerals (sand, silt, clay)
- 25% Air
- 25% Water
- 5% Organic matter

## Soil Testing
Test your soil every 2-3 years for:
- pH level (6.0-7.0 ideal for most crops)
- Nitrogen (N), Phosphorus (P), Potassium (K)
- Organic matter content
- Micronutrients (Fe, Zn, Mn, Cu)

## Improving Soil Health

### Add Organic Matter
- Compost: 2-4 inches annually
- Green manure: Plant cover crops like clover
- Aged manure: Apply 3-4 months before planting

### Balance pH
- **Too Acidic (pH < 6.0)**: Add lime (2-3 kg per 100 sq m)
- **Too Alkaline (pH > 7.5)**: Add sulfur or peat moss

### Enhance Drainage
- Add sand to clay soil (20-30% by volume)
- Create raised beds in poorly drained areas
- Install drainage tiles for severe waterlogging

## Maintaining Soil Health
- Practice no-till or minimal tillage
- Use mulch to prevent erosion
- Rotate crops to prevent nutrient depletion
- Avoid compaction from heavy machinery
'''
        },
        {
            'title': 'Wheat Cultivation: From Seed to Harvest',
            'summary': 'Complete guide to growing wheat, including variety selection, planting techniques, and harvest timing.',
            'category': 'crop-cultivation',
            'difficulty_level': 'intermediate',
            'reading_time': 15,
            'crop_type': 'wheat',
            'tags': 'wheat, cereals, cultivation, harvest',
            'content': '''# Wheat Cultivation Guide

## Variety Selection
Choose based on your region:
- **Winter Wheat**: Plant in fall, harvest in summer (higher yields)
- **Spring Wheat**: Plant in spring, harvest in fall (shorter season)
- **Durum Wheat**: For pasta production (requires hot, dry climate)

## Land Preparation
1. Deep plowing (20-25 cm) after previous crop harvest
2. Apply farmyard manure (10-15 tons/hectare)
3. Level field for uniform water distribution
4. Create proper drainage channels

## Sowing
- **Timing**: October-November (winter), March-April (spring)
- **Seed Rate**: 100-125 kg/hectare
- **Row Spacing**: 20-23 cm
- **Depth**: 5-6 cm
- **Method**: Seed drill for uniform distribution

## Nutrient Management
- **Basal Application**: 60 kg N + 60 kg P₂O₅ + 40 kg K₂O per hectare
- **Top Dressing**: 60 kg N at tillering stage (21 days after sowing)
- **Second Top Dressing**: 60 kg N at jointing stage (40-45 days)

## Irrigation Schedule
- **Critical Stages**: Crown root initiation (20-25 days), tillering (40-45 days), flowering (60-65 days), milk stage (80-85 days), dough stage (100-105 days)
- **Total Water**: 4-6 irrigations depending on soil and climate

## Pest and Disease Management
- **Aphids**: Use neem oil or imidacloprid
- **Rust**: Apply propiconazole fungicide
- **Termites**: Treat seeds with chlorpyrifos

## Harvesting
- **Timing**: When moisture content drops to 20-25%
- **Method**: Combine harvester for large fields
- **Yield**: 40-50 quintals/hectare (irrigated), 20-25 quintals/hectare (rainfed)
'''
        },
        {
            'title': 'Smart Farming with IoT: Sensors and Automation',
            'summary': 'Discover how IoT sensors and automation can optimize your farm operations and increase productivity.',
            'category': 'agricultural-technology',
            'difficulty_level': 'advanced',
            'reading_time': 12,
            'crop_type': 'general',
            'tags': 'IoT, smart-farming, sensors, automation, technology',
            'content': '''# Smart Farming with IoT

## Essential IoT Sensors for Farms

### 1. Soil Sensors
- **Moisture Sensors**: Monitor soil water content (₹2,000-5,000)
- **pH Sensors**: Track soil acidity (₹3,000-8,000)
- **NPK Sensors**: Measure nutrient levels (₹15,000-30,000)

### 2. Weather Stations
- Temperature, humidity, rainfall monitoring
- Wind speed and direction
- Solar radiation measurement
- Cost: ₹20,000-50,000

### 3. Crop Health Sensors
- NDVI cameras for vegetation health
- Multispectral imaging
- Disease detection sensors

## Automation Systems

### Automated Irrigation
- Soil moisture-based triggering
- Weather forecast integration
- Mobile app control
- Water savings: 30-50%

### Drone Technology
- Crop health monitoring
- Precision spraying
- Aerial mapping
- Cost: ₹50,000-3,00,000

## Implementation Steps
1. Start with basic soil moisture sensors
2. Add weather station for climate data
3. Integrate with automated irrigation
4. Expand to crop monitoring systems
5. Implement data analytics platform

## ROI Expectations
- Initial Investment: ₹1-5 lakhs
- Water Savings: 30-50%
- Yield Increase: 15-25%
- Labor Reduction: 40-60%
- Payback Period: 2-3 years
'''
        },
        {
            'title': 'Tomato Farming: High-Yield Techniques',
            'summary': 'Maximize your tomato yields with proven cultivation methods, pest management, and post-harvest handling.',
            'category': 'crop-cultivation',
            'difficulty_level': 'beginner',
            'reading_time': 10,
            'crop_type': 'tomato',
            'tags': 'tomato, vegetables, high-yield, cultivation',
            'content': '''# High-Yield Tomato Farming

## Variety Selection
**Hybrid Varieties (Higher Yield):**
- Arka Rakshak (disease resistant)
- Pusa Ruby (determinate, good for processing)
- Himsona (indeterminate, long harvest period)

**Open-Pollinated:**
- Desi varieties for local markets
- Better flavor but lower yields

## Nursery Management
- **Seed Treatment**: Trichoderma @ 4g/kg seeds
- **Sowing**: In pro-trays or raised beds
- **Transplanting Age**: 25-30 days (4-5 true leaves)

## Field Preparation
- Deep plowing and leveling
- Apply FYM: 25-30 tons/hectare
- Create raised beds (15 cm height)
- Install drip irrigation system

## Planting
- **Spacing**: 60 cm × 45 cm (determinate), 75 cm × 60 cm (indeterminate)
- **Population**: 25,000-30,000 plants/hectare
- **Staking**: Essential for indeterminate varieties

## Fertigation Schedule
- **Week 1-2**: 19:19:19 @ 5 kg/hectare
- **Week 3-6**: 13:0:45 @ 8 kg/hectare
- **Week 7-12**: 12:61:0 @ 10 kg/hectare
- **Micronutrients**: Spray every 15 days

## Pest Management
- **Early Blight**: Mancozeb spray
- **Fruit Borer**: Pheromone traps + Bt spray
- **Whitefly**: Yellow sticky traps + neem oil

## Harvesting
- **Timing**: 60-90 days after transplanting
- **Frequency**: Every 3-4 days
- **Yield**: 60-80 tons/hectare (hybrid), 40-50 tons/hectare (OP)
'''
        },
        {
            'title': 'Composting 101: Turn Waste into Black Gold',
            'summary': 'Learn how to create nutrient-rich compost from farm and kitchen waste to improve soil fertility naturally.',
            'category': 'sustainable-farming',
            'difficulty_level': 'beginner',
            'reading_time': 6,
            'crop_type': 'general',
            'tags': 'composting, organic, waste-management, soil-health',
            'content': '''# Composting 101

## What is Compost?
Compost is decomposed organic matter that enriches soil with nutrients and beneficial microorganisms.

## Materials Needed

### Green Materials (Nitrogen-Rich)
- Fresh grass clippings
- Kitchen vegetable scraps
- Coffee grounds
- Fresh manure
- Green leaves

### Brown Materials (Carbon-Rich)
- Dry leaves
- Straw and hay
- Sawdust
- Shredded paper
- Cardboard

## The Perfect Recipe
- **Ratio**: 3 parts brown : 1 part green (by volume)
- **Moisture**: Like a wrung-out sponge (40-60%)
- **Air**: Turn pile every 7-10 days
- **Size**: Minimum 1 cubic meter for proper heating

## Composting Methods

### 1. Hot Composting (Fast - 6-8 weeks)
- Build pile all at once
- Maintain 55-65°C temperature
- Turn every 3-4 days
- Ready in 6-8 weeks

### 2. Cold Composting (Slow - 6-12 months)
- Add materials gradually
- Minimal turning
- Lower temperature
- Takes longer but less effort

### 3. Vermicomposting (Worm Composting)
- Use Eisenia fetida (red wigglers)
- Process kitchen waste quickly
- Produces high-quality compost
- Ideal for small spaces

## Troubleshooting
- **Smells Bad**: Too wet or too much green material (add browns)
- **Not Heating**: Too dry or too small (add water, increase size)
- **Attracts Pests**: Don't add meat, dairy, or oils

## Using Compost
- **Application Rate**: 2-4 inches on garden beds
- **Timing**: 2-4 weeks before planting
- **Storage**: Keep moist and covered
'''
        },
        {
            'title': 'Rice Paddy Management: Traditional and Modern Methods',
            'summary': 'Comprehensive guide to rice cultivation covering both traditional flooding and modern SRI techniques.',
            'category': 'crop-cultivation',
            'difficulty_level': 'intermediate',
            'reading_time': 14,
            'crop_type': 'rice',
            'tags': 'rice, paddy, SRI, cultivation, water-management',
            'content': '''# Rice Paddy Management

## Variety Selection
**Short Duration (90-100 days):**
- Swarna Sub-1 (flood tolerant)
- Sahbhagi Dhan (drought tolerant)

**Medium Duration (120-130 days):**
- IR-64, Samba Mahsuri
- Higher yield potential

**Long Duration (140-150 days):**
- Basmati varieties
- Premium market price

## Traditional Flooding Method

### Nursery Preparation
- **Seed Rate**: 40-50 kg/hectare
- **Nursery Area**: 1000 sq m per hectare
- **Transplanting Age**: 25-30 days

### Main Field Preparation
- Puddling: 2-3 passes with rotavator
- Leveling for uniform water depth
- Bund strengthening to prevent water loss

### Water Management
- Maintain 5-7 cm standing water
- Drain 7 days before harvest
- Total water requirement: 1200-1500 mm

## System of Rice Intensification (SRI)

### Key Principles
- Young seedlings (8-12 days old)
- Single seedling per hill
- Wide spacing (25 cm × 25 cm)
- Alternate wetting and drying
- Mechanical weeding

### Benefits
- 20-30% higher yield
- 40-50% water savings
- Stronger, healthier plants
- Lower seed requirement (5-6 kg/hectare)

## Nutrient Management
- **Basal**: 60 kg N + 30 kg P₂O₅ + 30 kg K₂O
- **Top Dressing 1**: 60 kg N at tillering (21 days)
- **Top Dressing 2**: 60 kg N at panicle initiation (42 days)
- **Zinc**: 25 kg ZnSO₄/hectare if deficient

## Pest and Disease Control
- **Stem Borer**: Pheromone traps + Cartap hydrochloride
- **Blast**: Tricyclazole spray
- **Brown Plant Hopper**: Imidacloprid seed treatment

## Harvesting
- **Timing**: When 80% grains turn golden yellow
- **Moisture**: 20-22% for safe storage
- **Yield**: 50-60 quintals/hectare (traditional), 60-80 quintals/hectare (SRI)
'''
        },
        {
            'title': 'Market Trends 2025: What Crops to Grow for Maximum Profit',
            'summary': 'Analysis of current market trends and price forecasts to help you make informed crop selection decisions.',
            'category': 'market-trends',
            'difficulty_level': 'intermediate',
            'reading_time': 9,
            'crop_type': 'general',
            'tags': 'market-analysis, pricing, profit, crop-selection',
            'content': '''# Market Trends 2025

## High-Demand Crops

### 1. Organic Vegetables (Premium Prices)
- **Market Growth**: 25% annually
- **Price Premium**: 30-50% over conventional
- **Top Crops**: Tomatoes, leafy greens, bell peppers
- **Certification**: Required for premium pricing

### 2. Millets (Government Push)
- **Support Price**: Increased by 20%
- **Export Demand**: Growing in health-conscious markets
- **Varieties**: Finger millet, pearl millet, foxtail millet
- **Subsidy**: Available for millet cultivation

### 3. Medicinal Plants
- **Ashwagandha**: ₹200-300/kg
- **Tulsi**: ₹150-200/kg
- **Aloe Vera**: ₹15-20/kg
- **Contract Farming**: Available with pharma companies

### 4. Exotic Vegetables
- **Broccoli**: ₹40-60/kg
- **Zucchini**: ₹50-80/kg
- **Lettuce**: ₹100-150/kg
- **Market**: Urban areas, restaurants, hotels

## Price Forecast Analysis

### Cereals
- Wheat: Stable (₹2,125/quintal MSP)
- Rice: Slight increase expected
- Maize: Growing demand from poultry sector

### Pulses
- Tur Dal: High demand, good prices
- Moong: Short duration, good returns
- Chana: Stable market

### Cash Crops
- Cotton: Volatile, depends on global market
- Sugarcane: Stable with FRP support
- Soybean: Growing demand for oil

## Risk Management Strategies
1. Diversify crops (don't put all eggs in one basket)
2. Use contract farming for price security
3. Store produce during glut, sell during shortage
4. Join farmer producer organizations (FPOs)
5. Use commodity futures for price hedging

## Value Addition Opportunities
- Processing (dried vegetables, pickles)
- Packaging for retail market
- Direct marketing through online platforms
- Organic certification for premium pricing
'''
        },
        {
            'title': 'Drip Irrigation vs Sprinkler: Which is Right for Your Farm?',
            'summary': 'Compare drip and sprinkler irrigation systems to choose the most efficient and cost-effective option.',
            'category': 'irrigation-techniques',
            'difficulty_level': 'beginner',
            'reading_time': 8,
            'crop_type': 'general',
            'tags': 'irrigation, comparison, water-efficiency, cost-analysis',
            'content': '''# Drip vs Sprinkler Irrigation

## Drip Irrigation

### Advantages
- **Water Efficiency**: 90-95% (highest)
- **Fertilizer Application**: Direct to roots (fertigation)
- **Weed Control**: Only irrigates crop area
- **Disease Prevention**: Keeps foliage dry
- **Suitable For**: Row crops, orchards, vegetables

### Disadvantages
- **Initial Cost**: ₹50,000-80,000/hectare
- **Maintenance**: Requires regular cleaning
- **Clogging**: Risk with poor water quality
- **Lifespan**: 5-7 years

### Best For
- High-value crops (vegetables, fruits)
- Water-scarce regions
- Precise nutrient management
- Sloping land

## Sprinkler Irrigation

### Advantages
- **Coverage**: Large area quickly
- **Cooling Effect**: Beneficial in hot weather
- **Flexibility**: Easy to move and adjust
- **Lower Cost**: ₹30,000-50,000/hectare
- **Suitable For**: Field crops, lawns, orchards

### Disadvantages
- **Water Efficiency**: 70-80%
- **Wind Effect**: Uneven distribution in windy conditions
- **Disease Risk**: Wet foliage can promote diseases
- **Energy Cost**: Higher pump requirements

### Types
1. **Fixed Sprinkler**: Permanent installation
2. **Semi-Portable**: Move between fields
3. **Center Pivot**: Large circular fields
4. **Rain Gun**: High discharge, large area

## Cost Comparison (Per Hectare)

### Drip System
- **Installation**: ₹60,000-80,000
- **Annual Maintenance**: ₹5,000-8,000
- **Water Savings**: 40-50%
- **Yield Increase**: 20-30%

### Sprinkler System
- **Installation**: ₹35,000-50,000
- **Annual Maintenance**: ₹3,000-5,000
- **Water Savings**: 25-35%
- **Yield Increase**: 10-15%

## Decision Matrix

**Choose Drip If:**
- Growing high-value crops
- Water is scarce or expensive
- Need precise fertigation
- Have undulating terrain

**Choose Sprinkler If:**
- Growing field crops (wheat, maize)
- Have flat, large fields
- Initial budget is limited
- Need cooling effect for crops

## Subsidy Information
- **Drip**: 55-90% subsidy (varies by state)
- **Sprinkler**: 50-80% subsidy
- **Small Farmers**: Higher subsidy percentage
- **Apply Through**: District agriculture office
'''
        },
        {
            'title': 'Crop Rotation: Boost Yields and Soil Health',
            'summary': 'Master the art of crop rotation to improve soil fertility, break pest cycles, and increase farm profitability.',
            'category': 'sustainable-farming',
            'difficulty_level': 'intermediate',
            'reading_time': 11,
            'crop_type': 'general',
            'tags': 'crop-rotation, soil-health, sustainable, planning',
            'content': '''# Crop Rotation Strategies

## Why Rotate Crops?

### Benefits
1. **Soil Fertility**: Different crops use different nutrients
2. **Pest Control**: Breaks pest and disease cycles
3. **Weed Management**: Different crops suppress different weeds
4. **Soil Structure**: Deep and shallow roots improve soil
5. **Income Stability**: Diversified income sources

## Basic Rotation Principles

### Crop Families
- **Legumes**: Fix nitrogen (beans, peas, lentils)
- **Brassicas**: Heavy feeders (cabbage, cauliflower)
- **Solanaceae**: Moderate feeders (tomato, potato, eggplant)
- **Cucurbits**: Moderate feeders (cucumber, melon, squash)
- **Cereals**: Light feeders (wheat, rice, maize)

### Golden Rules
1. Don't grow same family in succession
2. Follow heavy feeders with legumes
3. Alternate deep and shallow-rooted crops
4. Include cover crops in rotation

## Sample Rotation Plans

### 3-Year Rotation (Small Farm)
**Year 1**: Legumes (beans/peas) - Nitrogen fixation
**Year 2**: Heavy feeders (tomatoes/cabbage) - Use fixed nitrogen
**Year 3**: Light feeders (wheat/maize) - Soil rest

### 4-Year Rotation (Medium Farm)
**Year 1**: Legumes (soybeans)
**Year 2**: Cereals (wheat)
**Year 3**: Root crops (potatoes)
**Year 4**: Brassicas (mustard) + Cover crop

### 5-Year Rotation (Large Farm)
**Year 1**: Legumes (chickpeas)
**Year 2**: Cereals (wheat)
**Year 3**: Oilseeds (sunflower)
**Year 4**: Vegetables (tomatoes)
**Year 5**: Cereals (maize) + Cover crop

## Cover Crops in Rotation

### Winter Cover Crops
- **Rye**: Suppresses weeds, adds organic matter
- **Clover**: Fixes nitrogen, improves soil
- **Vetch**: Nitrogen fixation, weed suppression

### Summer Cover Crops
- **Cowpea**: Quick nitrogen fixation
- **Sorghum**: Biomass production
- **Sunhemp**: Nematode suppression

## Economic Benefits

### Yield Improvements
- 15-20% higher yields with proper rotation
- Reduced fertilizer costs (30-40%)
- Lower pesticide use (40-50%)
- Better soil water retention

### Risk Reduction
- Diversified income streams
- Market price fluctuation buffer
- Weather risk distribution
- Pest outbreak protection

## Planning Your Rotation

### Step 1: Assess Your Land
- Soil type and fertility
- Water availability
- Climate and season length
- Market access

### Step 2: Choose Crops
- Select 3-5 compatible crops
- Consider market demand
- Match to your resources
- Include nitrogen-fixing legumes

### Step 3: Create Schedule
- Map out 3-5 year plan
- Include cover crops
- Plan for equipment needs
- Schedule labor requirements

### Step 4: Monitor and Adjust
- Track yields and soil health
- Record pest and disease issues
- Adjust based on results
- Update plan annually
'''
        },
        {
            'title': 'Greenhouse Farming: Year-Round Production Guide',
            'summary': 'Learn how to set up and manage a greenhouse for controlled environment agriculture and off-season production.',
            'category': 'agricultural-technology',
            'difficulty_level': 'advanced',
            'reading_time': 13,
            'crop_type': 'general',
            'tags': 'greenhouse, protected-cultivation, technology, high-value',
            'content': '''# Greenhouse Farming Guide

## Types of Greenhouses

### 1. Naturally Ventilated (Low-Cost)
- **Cost**: ₹600-800/sq m
- **Structure**: Bamboo/GI pipe frame
- **Covering**: UV-stabilized polyethylene (200 micron)
- **Suitable For**: Tropical and subtropical regions

### 2. Fan and Pad Cooled
- **Cost**: ₹1,200-1,500/sq m
- **Cooling**: Evaporative cooling pads
- **Control**: Semi-automated
- **Suitable For**: Hot, dry climates

### 3. Fully Automated (High-Tech)
- **Cost**: ₹2,500-4,000/sq m
- **Features**: Climate control, fertigation, CO₂ enrichment
- **Monitoring**: Computer-controlled
- **Suitable For**: High-value crops, research

## Site Selection

### Requirements
- **Sunlight**: Minimum 6-8 hours direct sunlight
- **Water**: Reliable source with good quality
- **Drainage**: Gentle slope for water runoff
- **Wind**: Protected from strong winds
- **Access**: Good road connectivity for transport

### Orientation
- **East-West**: Better for winter production
- **North-South**: Better for summer production
- **Ridge Height**: 4-5 meters for better ventilation

## Crop Selection

### High-Value Crops
**Vegetables:**
- Tomato (₹80-120/kg off-season)
- Capsicum (₹100-150/kg)
- Cucumber (₹40-60/kg)
- Lettuce (₹150-200/kg)

**Flowers:**
- Rose (₹5-15/stem)
- Gerbera (₹8-12/stem)
- Carnation (₹10-20/stem)

### Yield Comparison
- **Open Field Tomato**: 40-50 tons/hectare
- **Greenhouse Tomato**: 150-200 tons/hectare
- **Production Cycle**: Year-round vs seasonal

## Climate Control

### Temperature Management
- **Optimal Range**: 20-30°C (day), 15-20°C (night)
- **Cooling**: Shade nets, foggers, exhaust fans
- **Heating**: Hot air blowers (winter in cold regions)

### Humidity Control
- **Ideal Range**: 60-70%
- **Too High**: Increase ventilation, use dehumidifiers
- **Too Low**: Use foggers, reduce ventilation

### CO₂ Enrichment
- **Natural**: Organic matter decomposition
- **Artificial**: CO₂ generators (1000-1500 ppm)
- **Benefit**: 20-30% yield increase

## Growing Systems

### 1. Soil-Based
- **Pros**: Lower cost, familiar to farmers
- **Cons**: Disease risk, soil degradation
- **Preparation**: Sterilization, organic matter addition

### 2. Soilless (Hydroponics)
- **Pros**: Higher yields, no soil diseases, water efficient
- **Cons**: Higher initial cost, technical knowledge required
- **Systems**: NFT, DFT, Dutch bucket

### 3. Substrate Culture
- **Media**: Cocopeat, perlite, vermiculite
- **Pros**: Good drainage, reusable
- **Fertigation**: Automated nutrient delivery

## Economics

### Investment (1000 sq m)
- **Structure**: ₹6-8 lakhs
- **Irrigation**: ₹50,000-1 lakh
- **Growing System**: ₹1-2 lakhs
- **Total**: ₹8-12 lakhs

### Returns (Annual)
- **Tomato Production**: 15-20 tons
- **Revenue**: ₹12-18 lakhs (₹80/kg average)
- **Operating Cost**: ₹4-6 lakhs
- **Net Profit**: ₹6-10 lakhs
- **ROI**: 50-80% annually

### Subsidy
- **NABARD**: 50% subsidy (up to ₹28 lakhs/hectare)
- **State Schemes**: Additional 10-20%
- **Eligibility**: Small and marginal farmers priority
'''
        },
        {
            'title': 'Banana Cultivation: Complete Commercial Guide',
            'summary': 'Step-by-step guide to commercial banana farming including variety selection, planting, and disease management.',
            'category': 'crop-cultivation',
            'difficulty_level': 'intermediate',
            'reading_time': 12,
            'crop_type': 'banana',
            'tags': 'banana, fruits, commercial, high-yield',
            'content': '''# Commercial Banana Cultivation

## Variety Selection

### Tissue Culture vs Suckers
**Tissue Culture (Recommended):**
- Disease-free planting material
- Uniform growth and maturity
- 20-30% higher yield
- Cost: ₹12-15 per plant

**Suckers (Traditional):**
- Lower cost (₹5-8 per plant)
- Risk of disease transmission
- Variable growth

### Popular Varieties
**Grand Naine (G9):**
- Yield: 40-50 kg/plant
- Height: 2-2.5 meters
- Cycle: 11-12 months
- Market: Export and domestic

**Robusta:**
- Yield: 25-30 kg/plant
- Hardy variety
- Cycle: 12-14 months
- Market: Domestic

**Red Banana:**
- Yield: 15-20 kg/plant
- Premium price (₹60-80/kg)
- Cycle: 13-15 months
- Market: Niche, urban

## Land Preparation

### Soil Requirements
- **Type**: Well-drained loamy soil
- **pH**: 6.5-7.5
- **Depth**: Minimum 60 cm
- **Organic Matter**: 2-3%

### Pit Preparation
- **Size**: 60 cm × 60 cm × 60 cm
- **Spacing**: 1.8 m × 1.8 m (3,000 plants/hectare)
- **Filling**: FYM (10 kg) + topsoil + neem cake (200g)

## Planting

### Best Season
- **Monsoon**: June-July (rainfed)
- **Summer**: February-March (irrigated)
- **Avoid**: Winter planting in cold regions

### Planting Method
1. Place tissue culture plant in center of pit
2. Fill with soil mixture
3. Water immediately (10 liters)
4. Mulch with dry leaves or plastic

## Irrigation

### Water Requirements
- **Critical Stages**: Vegetative growth, flowering, fruit development
- **Frequency**: Every 4-5 days (summer), 7-10 days (winter)
- **Method**: Drip irrigation (4 liters/hour/plant)
- **Annual Requirement**: 2000-2500 mm

## Nutrition Management

### Fertilizer Schedule (Per Plant/Year)
**Organic:**
- FYM: 20-25 kg
- Neem cake: 1 kg

**Inorganic:**
- Nitrogen: 200-250g
- Phosphorus: 60-80g
- Potassium: 300-350g

### Application Timing
- **Month 1-3**: 25% of total
- **Month 4-6**: 35% of total
- **Month 7-9**: 40% of total

## Pest and Disease Management

### Major Diseases
**Panama Wilt (Fusarium):**
- Symptoms: Yellowing, wilting
- Control: Use resistant varieties, crop rotation
- Prevention: Tissue culture plants

**Sigatoka (Leaf Spot):**
- Symptoms: Brown spots on leaves
- Control: Propiconazole spray
- Prevention: Remove affected leaves

### Major Pests
**Banana Weevil:**
- Damage: Tunnels in pseudostem
- Control: Pheromone traps, fipronil application
- Prevention: Clean planting material

**Aphids:**
- Damage: Virus transmission
- Control: Imidacloprid spray
- Prevention: Remove alternate hosts

## Harvesting

### Maturity Indicators
- **Age**: 90-120 days after flowering
- **Fullness**: Fingers become round
- **Color**: Green with slight yellowing

### Harvesting Method
- Cut bunch with sharp knife
- Leave 30 cm stalk
- Handle carefully to avoid bruising
- Harvest in morning hours

## Post-Harvest

### Ripening
- **Natural**: 5-7 days at room temperature
- **Artificial**: Ethylene gas (24-48 hours)
- **Temperature**: 18-20°C
- **Humidity**: 90-95%

### Packaging
- Corrugated boxes (10-15 kg)
- Cushioning material
- Ventilation holes
- Grade marking

## Economics (Per Hectare)

### Investment
- **Planting Material**: ₹40,000-45,000
- **Fertilizers**: ₹30,000-35,000
- **Irrigation**: ₹25,000-30,000
- **Plant Protection**: ₹15,000-20,000
- **Labor**: ₹40,000-50,000
- **Total**: ₹1.5-1.8 lakhs

### Returns
- **Yield**: 40-50 tons/hectare
- **Price**: ₹20-30/kg (average)
- **Revenue**: ₹8-15 lakhs
- **Net Profit**: ₹6-12 lakhs
- **ROI**: 300-600%
'''
        },
        {
            'title': 'Water Harvesting Techniques for Sustainable Farming',
            'summary': 'Implement rainwater harvesting and conservation methods to ensure water security for your farm.',
            'category': 'sustainable-farming',
            'difficulty_level': 'intermediate',
            'reading_time': 10,
            'crop_type': 'general',
            'tags': 'water-harvesting, conservation, sustainability, irrigation',
            'content': '''# Water Harvesting Techniques

## Why Harvest Rainwater?

### Benefits
- **Water Security**: Reduce dependence on groundwater
- **Cost Savings**: Lower irrigation costs
- **Groundwater Recharge**: Improve water table
- **Flood Control**: Reduce runoff and erosion
- **Subsidy**: Government support available

## Rainwater Harvesting Structures

### 1. Farm Ponds
**Design:**
- **Size**: 20m × 20m × 3m (1200 cubic meters)
- **Location**: Lowest point of farm
- **Lining**: HDPE liner or clay
- **Cost**: ₹1.5-2.5 lakhs

**Benefits:**
- Storage capacity for 2-3 irrigations
- Fish farming opportunity
- Microclimate improvement
- Subsidy: 50-70%

### 2. Check Dams
**Purpose:** Slow down water flow, increase infiltration
**Types:**
- **Loose Boulder**: ₹50,000-1 lakh
- **Gabion**: ₹1-2 lakhs
- **Concrete**: ₹2-5 lakhs

**Suitable For:**
- Seasonal streams
- Sloping land
- Community projects

### 3. Percolation Tanks
**Function:** Recharge groundwater
**Design:**
- **Depth**: 2-3 meters
- **Area**: 0.5-2 hectares
- **Location**: Permeable soil area

**Impact:**
- Raises water table in 500m radius
- Benefits multiple farmers
- Long-term solution

### 4. Contour Bunding
**Purpose:** Reduce runoff, increase infiltration
**Specifications:**
- **Height**: 0.5-1 meter
- **Top Width**: 1-1.5 meters
- **Spacing**: Based on slope (20-40 meters)

**Benefits:**
- Prevents soil erosion
- Increases soil moisture
- Low cost (₹15,000-25,000/hectare)

## Roof Water Harvesting

### Components
1. **Catchment**: Roof area (100 sq m = 100,000 liters/year @ 1000mm rainfall)
2. **Gutters**: PVC or metal (₹100-200/meter)
3. **First Flush**: Diverts initial dirty water
4. **Storage**: Tanks (₹50-100/liter capacity)
5. **Filter**: Sand/gravel filter

### Calculation
**Annual Harvest = Roof Area (sq m) × Rainfall (mm) × 0.8 (efficiency)**
Example: 200 sq m × 1000 mm × 0.8 = 160,000 liters

## Micro-Irrigation Integration

### Drip Irrigation with Harvested Water
- **Filtration**: Essential for drip system
- **Storage**: Elevated tank for gravity flow
- **Savings**: 40-50% water compared to flood

### Sprinkler with Solar Pump
- **Solar Pump**: ₹1.5-3 lakhs (3-5 HP)
- **Subsidy**: 60-90% available
- **Operating Cost**: Minimal (no electricity)

## Soil Moisture Conservation

### Mulching
**Organic Mulch:**
- Straw, leaves, grass clippings
- Reduces evaporation by 50-70%
- Adds organic matter
- Cost: ₹5,000-10,000/hectare

**Plastic Mulch:**
- Black or silver polyethylene
- 70-80% water savings
- Weed control
- Cost: ₹15,000-20,000/hectare

### Conservation Tillage
- **Zero Tillage**: Minimal soil disturbance
- **Mulch Tillage**: Crop residue retention
- **Benefits**: Moisture retention, reduced erosion

## Economics

### Investment (Small Farm - 2 Hectares)
- **Farm Pond**: ₹2 lakhs (50% subsidy = ₹1 lakh)
- **Drip System**: ₹1.2 lakhs (55% subsidy = ₹54,000)
- **Solar Pump**: ₹2.5 lakhs (70% subsidy = ₹75,000)
- **Total Out-of-Pocket**: ₹2.29 lakhs

### Savings (Annual)
- **Electricity**: ₹30,000-40,000
- **Water Charges**: ₹20,000-30,000
- **Increased Yield**: ₹50,000-1 lakh
- **Total Benefit**: ₹1-1.7 lakhs/year
- **Payback**: 1.5-2.5 years

## Government Schemes

### PMKSY (Pradhan Mantri Krishi Sinchayee Yojana)
- **Farm Ponds**: 50-70% subsidy
- **Drip/Sprinkler**: 55-90% subsidy
- **Application**: Through agriculture department

### MGNREGA
- **Labor Cost**: 100% covered for water structures
- **Material**: Partial support
- **Eligibility**: Small and marginal farmers

### State Schemes
- Varies by state
- Additional 10-20% subsidy
- Check with local agriculture office
'''
        },
        {
            'title': 'Precision Agriculture: Using Data to Optimize Farming',
            'summary': 'Leverage GPS, sensors, and data analytics to make informed decisions and maximize farm efficiency.',
            'category': 'agricultural-technology',
            'difficulty_level': 'advanced',
            'reading_time': 11,
            'crop_type': 'general',
            'tags': 'precision-agriculture, GPS, data-analytics, technology',
            'content': '''# Precision Agriculture

## What is Precision Agriculture?

Precision agriculture uses technology to observe, measure, and respond to variability within fields to optimize returns while preserving resources.

## Core Technologies

### 1. GPS and GNSS
**Applications:**
- Auto-steering tractors (±2 cm accuracy)
- Variable rate application
- Field mapping
- Yield monitoring

**Benefits:**
- Reduce overlap (save 5-10% inputs)
- Straight rows for better management
- Accurate area measurement
- Cost: ₹50,000-3 lakhs

### 2. Remote Sensing
**Satellite Imagery:**
- NDVI (vegetation health)
- Soil moisture mapping
- Crop stress detection
- Free: Sentinel-2, Landsat
- Paid: Planet Labs (₹10,000-50,000/year)

**Drone Imaging:**
- High-resolution (5 cm/pixel)
- Multispectral cameras
- Weekly monitoring possible
- Cost: ₹50,000-3 lakhs (drone + camera)

### 3. Soil Sensors
**Types:**
- **Moisture**: ₹2,000-5,000 each
- **NPK**: ₹15,000-30,000 each
- **pH**: ₹3,000-8,000 each
- **EC (Salinity)**: ₹5,000-10,000 each

**Deployment:**
- 3-5 sensors per hectare
- Different depths (15, 30, 45 cm)
- Wireless data transmission
- Real-time monitoring

### 4. Variable Rate Technology (VRT)

**Variable Rate Seeding:**
- Adjust seed rate based on soil quality
- 10-15% seed savings
- Uniform crop stand
- Equipment cost: ₹5-10 lakhs

**Variable Rate Fertilization:**
- Apply nutrients based on soil tests
- 20-30% fertilizer savings
- Reduced environmental impact
- Equipment cost: ₹3-8 lakhs

**Variable Rate Irrigation:**
- Zone-based water application
- 30-40% water savings
- Prevent over/under watering
- System cost: ₹60,000-1.2 lakhs/hectare

## Data Management

### Farm Management Software
**Features:**
- Field mapping
- Input tracking
- Yield monitoring
- Financial analysis
- Weather integration

**Options:**
- **Free**: FarmLogs, Cropio
- **Paid**: John Deere Operations Center, Climate FieldView
- **Cost**: ₹10,000-50,000/year

### Data Collection
- Soil test results
- Weather data
- Crop health images
- Yield maps
- Input application records

### Data Analysis
- Identify patterns
- Predict yields
- Optimize inputs
- Benchmark performance

## Implementation Strategy

### Phase 1: Basic (Year 1)
**Investment**: ₹50,000-1 lakh
- Soil testing (grid sampling)
- Weather station
- Basic GPS for field mapping
- Free satellite imagery

**Benefits:**
- 10-15% input optimization
- Better record keeping
- Informed decisions

### Phase 2: Intermediate (Year 2-3)
**Investment**: ₹2-4 lakhs
- Soil moisture sensors
- Drone for crop monitoring
- Variable rate fertilizer spreader
- Farm management software

**Benefits:**
- 20-25% input savings
- Early problem detection
- Improved yields (10-15%)

### Phase 3: Advanced (Year 4+)
**Investment**: ₹5-10 lakhs
- Auto-steer tractor
- Complete VRT system
- Advanced analytics
- AI-based decision support

**Benefits:**
- 30-40% input optimization
- 20-25% yield increase
- Reduced labor (30-40%)

## ROI Analysis

### Small Farm (5 Hectares)
**Annual Investment**: ₹1-2 lakhs
**Savings:**
- Inputs: ₹50,000-1 lakh
- Labor: ₹30,000-50,000
- Yield increase: ₹1-2 lakhs
**Net Benefit**: ₹80,000-2.5 lakhs
**Payback**: 1-2 years

### Medium Farm (20 Hectares)
**Annual Investment**: ₹4-6 lakhs
**Savings:**
- Inputs: ₹2-4 lakhs
- Labor: ₹1-2 lakhs
- Yield increase: ₹4-8 lakhs
**Net Benefit**: ₹3-10 lakhs
**Payback**: 1-1.5 years

## Challenges and Solutions

### Challenge 1: High Initial Cost
**Solution:**
- Start with basic technologies
- Use government subsidies (30-50%)
- Form farmer groups to share equipment
- Lease instead of buy

### Challenge 2: Technical Knowledge
**Solution:**
- Training programs (KVK, agriculture universities)
- Hire precision ag consultant
- Online courses and webinars
- Vendor support

### Challenge 3: Data Connectivity
**Solution:**
- Offline data collection
- Sync when internet available
- Use mobile hotspots
- Satellite internet (Starlink)

## Future Trends

- **AI and Machine Learning**: Predictive analytics
- **Robotics**: Autonomous tractors and harvesters
- **Blockchain**: Supply chain transparency
- **5G**: Real-time data transmission
- **Edge Computing**: On-farm data processing
'''
        }
    ]
    
    return articles_data

def seed_articles():
    """Main function to seed articles"""
    print("=" * 70)
    print("FarmLink AI - Learning Hub Article Seeder")
    print("=" * 70)
    
    # Get admin user
    admin = get_admin_user()
    if not admin:
        return
    
    print(f"\nAdmin user found: {admin.full_name} (ID: {admin.id})")
    print(f"Creating 15 comprehensive articles...\n")
    
    # Get articles data
    articles_data = create_articles(admin.id)
    
    # Create articles
    created_count = 0
    skipped_count = 0
    
    for idx, article_data in enumerate(articles_data, 1):
        # Check if article already exists
        existing = LearningArticle.query.filter_by(
            title=article_data['title']
        ).first()
        
        if existing:
            print(f"[{idx}/15] ⏭️  Skipped: '{article_data['title']}' (already exists)")
            skipped_count += 1
            continue
        
        try:
            article = LearningArticle(
                title=article_data['title'],
                content=article_data['content'],
                summary=article_data['summary'],
                category=article_data['category'],
                difficulty_level=article_data['difficulty_level'],
                reading_time=article_data['reading_time'],
                crop_type=article_data.get('crop_type'),
                tags=article_data['tags'],
                author_id=admin.id,
                is_published=True,
                is_draft=False,
                views=0,
                likes=0,
                comments_count=0
            )
            
            db.session.add(article)
            db.session.commit()
            
            print(f"[{idx}/15] ✅ Created: '{article_data['title']}'")
            print(f"         Category: {article_data['category']} | Level: {article_data['difficulty_level']} | {article_data['reading_time']} min read")
            created_count += 1
            
        except Exception as e:
            db.session.rollback()
            print(f"[{idx}/15] ❌ Error creating '{article_data['title']}': {str(e)}")
    
    print("\n" + "=" * 70)
    print(f"✅ Successfully created: {created_count} articles")
    print(f"⏭️  Skipped (already exist): {skipped_count} articles")
    print(f"📚 Total articles in database: {LearningArticle.query.count()}")
    print("=" * 70)
    print("\n🎉 Seeding completed! Visit http://127.0.0.1:5000/learning-hub to view articles.")

if __name__ == '__main__':
    with app.app_context():
        seed_articles()
