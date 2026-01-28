"""
Central registry for all stock metrics used in the AI Stock Scorer.
This serves as the single source of truth for metric names, keys, weights, and scoring logic.
"""

from typing import Dict, List, Any

# Full metric definitions including prompts and scales
METRIC_DEFINITIONS = {
    'moat_score': {
        'display_name': 'Competitive Moat',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the competitive moat strength of {company_name} on a scale of 0-10, where:
- 0 = No competitive advantage, easily replaceable
- 5 = Moderate competitive advantages
- 10 = Extremely strong moat, nearly impossible to compete against

Consider factors like:
- Brand strength and customer loyalty
- Network effects
- Switching costs
- Economies of scale
- Patents/intellectual property
- Regulatory barriers
- Unique resources or capabilities

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'barriers_score': {
        'display_name': 'Barriers to Entry',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the barriers to entry for {company_name} on a scale of 0-10, where:
- 0 = No barriers, extremely easy for competitors to enter
- 5 = Moderate barriers to entry
- 10 = Extremely high barriers, nearly impossible for new competitors to enter

Consider factors like:
- Capital requirements
- Regulatory and licensing requirements
- Technological complexity
- Distribution channel access
- Brand recognition and customer loyalty
- Network effects
- Resource advantages
- Switching costs for customers

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'disruption_risk': {
        'display_name': 'Disruption Risk',
        'is_reverse': True,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the disruption risk for {company_name} on a scale of 0-10, where:
- 0 = No risk, very stable industry
- 5 = Moderate disruption risk
- 10 = Very high risk of being disrupted by new technology or competitors

Consider factors like:
- Technology disruption potential
- Regulatory risk
- Changing consumer preferences
- Emerging competitors with new business models
- Industry transformation trends
- Obsolescence risk
- Substitution threats

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'switching_cost': {
        'display_name': 'Switching Cost',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the switching costs for customers of {company_name} on a scale of 0-10, where:
- 0 = No switching costs, customers can easily leave
- 5 = Moderate switching costs
- 10 = Very high switching costs, customers are locked in

Consider factors like:
- Learning curve for new products
- Data migration complexity
- Contractual commitments
- Integration with existing systems
- Training requirements
- Financial switching costs
- Network effects making it hard to leave
- Compatibility issues

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'brand_strength': {
        'display_name': 'Brand Strength',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the brand strength for {company_name} on a scale of 0-10, where:
- 0 = No brand recognition or loyalty
- 5 = Moderate brand strength
- 10 = Extremely strong brand with high customer loyalty and recognition

Consider factors like:
- Brand recognition and awareness
- Customer loyalty and emotional attachment
- Brand reputation and trust
- Ability to charge premium prices
- Brand value and differentiation
- Marketing effectiveness
- Brand longevity and consistency
- Global brand presence

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'competition_intensity': {
        'display_name': 'Competition Intensity',
        'is_reverse': True,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the intensity of competition for {company_name} on a scale of 0-10, where:
- 0 = No competition, monopoly-like market
- 5 = Moderate competition
- 10 = Extremely intense competition with many aggressive competitors

Consider factors like:
- Number of competitors in the market
- Competitiveness of pricing strategies
- Aggressiveness of marketing and customer acquisition
- Market share fragmentation
- Barriers to market dominance
- Competitor capabilities and resources
- Frequency of competitive actions
- Market growth rate relative to competition

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'network_effect': {
        'display_name': 'Network Effect',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the network effects for {company_name} on a scale of 0-10, where:
- 0 = No network effects, value doesn't increase with more users
- 5 = Moderate network effects
- 10 = Extremely strong network effects, value increases dramatically with more users

Consider factors like:
- Value increases as more users join the network
- User count creates competitive advantage
- Network density and interconnectedness
- Platform effects and ecosystem benefits
- Data network effects
- Social network effects
- Two-sided market effects
- Viral growth potential

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'product_differentiation': {
        'display_name': 'Product Differentiation',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the product differentiation (vs commoditization) for {company_name} on a scale of 0-10, where:
- 0 = Completely commoditized, interchangeable with competitors, price competition
- 5 = Some differentiation, moderate pricing power
- 10 = Highly differentiated, unique products/services with strong pricing power

Consider factors like:
- Product uniqueness and distinctiveness
- Ability to command premium prices
- Customer perception of differentiation
- Brand differentiation and positioning
- R&D and innovation creating uniqueness
- Proprietary features or technology
- Service or experience differentiation
- Market positioning and specialization

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'innovativeness_score': {
        'display_name': 'Innovativeness',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the innovativeness of {company_name} on a scale of 0-10, where:
- 0 = Not innovative, relies on existing technologies and practices, minimal R&D
- 5 = Moderately innovative, some product improvements and incremental innovation
- 10 = Extremely innovative, breakthrough technologies, disruptive innovation, industry-leading R&D

Consider factors like:
- R&D investment and spending as percentage of revenue
- Patents, intellectual property, and technological breakthroughs
- Track record of introducing new products and services
- Innovation culture and ability to adapt to new technologies
- Leadership in developing new solutions or business models
- Speed of innovation cycles and time to market
- Investment in emerging technologies (AI, automation, etc.)
- Historical innovations and transformation initiatives

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'growth_opportunity': {
        'display_name': 'Growth Opportunity',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the growth opportunity for {company_name} on a scale of 0-10, where:
- 0 = Minimal growth opportunity, mature/declining market, limited expansion potential
- 5 = Moderate growth opportunity, steady market growth, some expansion possibilities
- 10 = Exceptional growth opportunity, rapidly expanding market, multiple growth vectors, high scalability

Consider factors like:
- Market size and growth rate of industry
- Addressable market size (TAM/SAM/SOM)
- Geographic expansion opportunities
- Product/service expansion potential
- Market penetration potential in existing segments
- Adjacent market opportunities
- Demographic and macroeconomic trends favoring growth
- Ability to scale operations efficiently
- Customer acquisition and retention growth potential
- International expansion opportunities
- Pricing power and margin expansion opportunities

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'riskiness_score': {
        'display_name': 'Business Risk',
        'is_reverse': True,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the overall riskiness of investing in {company_name} on a scale of 0-10, where:
- 0 = Very low risk, stable and predictable business model
- 5 = Moderate risk, some uncertainty in business outlook
- 10 = Very high risk, highly volatile or uncertain business model

Consider factors like:
- Financial risk and leverage/debt levels
- Business model stability and predictability
- Regulatory and legal risks
- Market volatility and cyclicality
- Management and execution risks
- Competitive and market position risks
- Technology and operational risks
- Macroeconomic sensitivity
- Dependency on key customers or suppliers
- Liquidity and financing risks
- Geographic and political risks
- Concentration risks

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'pricing_power': {
        'display_name': 'Pricing Power',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the pricing power of {company_name} on a scale of 0-10, where:
- 0 = No pricing power, commodity-like product with intense price competition
- 5 = Moderate pricing power, some ability to set prices above cost
- 10 = Exceptional pricing power, strong ability to raise prices without losing customers

Consider factors like:
- Ability to increase prices without significant demand loss
- Customer price sensitivity and elasticity
- Unique value proposition and differentiation
- Market position and competitive advantage
- Brand strength and customer loyalty
- Product/service necessity and switching costs
- Market concentration and competitive dynamics
- Substitution availability and alternatives
- Historical pricing power demonstrated
- Gross and operating margin trends
- Customer dependency and lock-in effects
- Regulatory or contractual pricing protections

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'ambition_score': {
        'display_name': 'Ambition',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the company and culture ambition of {company_name} on a scale of 0-10, where:
- 0 = Low ambition, complacent, maintaining status quo, no transformative goals
- 5 = Moderate ambition, some growth and improvement goals, incremental progress
- 10 = Extremely high ambition, transformative vision, aggressive growth targets, industry-changing goals

Consider factors like:
- Vision and mission clarity and boldness
- Growth targets and expansion ambitions
- Investment in R&D and innovation initiatives
- Market leadership aspirations
- Strategic initiatives and transformation programs
- Culture of excellence and high standards
- Long-term strategic planning and vision
- Willingness to take calculated risks for growth
- Executive leadership ambition and drive
- Company culture of continuous improvement
- Market disruption and category creation goals
- Global expansion and market dominance ambitions
- Investment in talent and capability building

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'bargaining_power_of_customers': {
        'display_name': 'Customer Bargaining Power',
        'is_reverse': True,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the bargaining power of customers for {company_name} on a scale of 0-10, where:
- 0 = Very low customer bargaining power, customers have no alternative options, company has strong pricing control
- 5 = Moderate customer bargaining power, some alternatives available, balanced negotiation power
- 10 = Very high customer bargaining power, many alternatives, customers can easily switch, strong price sensitivity

Consider factors like:
- Number of alternative suppliers and competitors available to customers
- Customer switching costs and ease of substitution
- Customer concentration and dependency on key accounts
- Customer ability to backward integrate
- Importance of company's products/services to customer
- Availability of information for price comparison
- Customer price sensitivity and elasticity
- Contractual or relationship-based power dynamics

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'bargaining_power_of_suppliers': {
        'display_name': 'Supplier Bargaining Power',
        'is_reverse': True,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the bargaining power of suppliers for {company_name} on a scale of 0-10, where:
- 0 = Very low supplier bargaining power, company has many alternative suppliers, strong negotiation leverage
- 5 = Moderate supplier bargaining power, some critical suppliers, balanced negotiation power
- 10 = Very high supplier bargaining power, company depends on few critical suppliers with high switching costs

Consider factors like:
- Number of alternative suppliers available to the company
- Supplier switching costs and ease of switching
- Supplier concentration and dependency on key accounts
- Supplier ability to forward integrate
- Importance of supplier's products/services to the company
- Availability of substitute inputs
- Supplier's product uniqueness and differentiation
- Impact of supplier inputs on company's product quality/price

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'product_quality_score': {
        'display_name': 'Product / Service Quality',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the product or service quality of {company_name} on a scale of 0-10, where:
- 0 = Poor quality, frequent complaints, low customer satisfaction, uncompetitive
- 5 = Moderate quality, meets industry standards, generally satisfied customers
- 10 = Exceptional quality, industry-leading performance, high customer satisfaction and loyalty

Consider factors like:
- Product/service performance and reliability
- Customer satisfaction and net promoter score (NPS)
- Product/service features and capabilities
- Design and user experience (UX)
- Durability and longevity
- Service and support quality
- Innovation and continuous improvement in quality
- Brand reputation for quality and excellence

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'culture_employee_satisfaction_score': {
        'display_name': 'Culture and Employee Satisfaction',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the company culture and employee satisfaction of {company_name} on a scale of 0-10, where:
- 0 = Poor culture, low employee morale, high turnover, negative environment
- 5 = Moderate culture, average employee satisfaction, stable environment
- 10 = Exceptional culture, high employee satisfaction, strong values, industry-leading workplace

Consider factors like:
- Employee engagement and morale
- Company values and mission alignment
- Diversity, equity, and inclusion (DEI) initiatives
- Professional development and growth opportunities
- Work-life balance and employee well-being
- Leadership and management effectiveness
- Compensation and benefits competitiveness
- Employee retention and turnover rates
- Internal communication and transparency
- Reputation as a top employer (Glassdoor ratings, etc.)

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'trailblazer_score': {
        'display_name': 'Trailblazer',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate {company_name} as a trailblazer or industry leader on a scale of 0-10, where:
- 0 = Laggard, follows others, slow to adapt, minimal industry impact
- 5 = Average industry player, stays competitive but rarely leads change
- 10 = Industry pioneer, sets trends, drives innovation, shapes the future of the market

Consider factors like:
- First-mover advantage in new categories or technologies
- Track record of creating new markets or disrupting existing ones
- Industry-wide recognition as a leader and innovator
- Ability to anticipate and shape future industry trends
- Influence on competitor strategies and industry standards
- Boldness in taking risks and pursuing transformative visions
- Speed of execution and adaptation to change
- Global impact and scale of leadership

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'management_quality_score': {
        'display_name': 'Management Quality',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the quality of management and leadership at {company_name} on a scale of 0-10, where:
- 0 = Poor leadership, lack of vision, ineffective execution, frequent scandals
- 5 = Competent management, steady execution, standard leadership
- 10 = Exceptional leadership, visionary, highly effective execution, strong integrity and track record

Consider factors like:
- Executive leadership vision and strategic thinking
- Track record of successful execution and value creation
- Integrity, ethics, and transparency
- Ability to attract and retain top talent
- Capital allocation skills and financial discipline
- Adaptability and resilience in changing markets
- Communication effectiveness with stakeholders
- Succession planning and management depth
- Reputation among investors, employees, and industry peers

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'ai_knowledge_score': {
        'display_name': 'AI Confidence',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the level of AI knowledge, adoption, and strategic focus at {company_name} on a scale of 0-10, where:
- 0 = No AI focus, minimal adoption or understanding, unaware of AI impact
- 5 = Moderate AI adoption, some AI-driven initiatives, basic understanding of AI potential
- 10 = Industry-leading AI capabilities, transformative AI strategy, deep expertise and integration

Consider factors like:
- Investment in AI research and development
- Integration of AI into products, services, and operations
- AI talent and expertise within the organization
- AI-driven innovation and competitive advantage
- Strategic partnerships and collaborations in AI
- AI governance, ethics, and responsible AI practices
- Track record of successful AI-driven transformations
- Vision for the future of AI within the company and industry

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'size_well_known_score': {
        'display_name': 'Size / Scale',
        'is_reverse': True,
        'weight': 19.31,
        'max_val': 10,
        'prompt': """Rate the size, scale, and market prominence of {company_name} on a scale of 0-10, where:
- 0 = Global giant, extremely well-known, massive scale and resources
- 5 = Large, well-established company with significant market presence
- 10 = Small, niche player, limited scale and recognition

Consider factors like:
- Market capitalization and enterprise value
- Annual revenue and profitability scale
- Number of employees and global presence
- Brand awareness and recognition among consumers and investors
- Market share and dominance in key segments
- Scale of operations, distribution, and infrastructure
- Influence on industry and macroeconomic trends
- Visibility in financial media and public discourse

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'ethical_healthy_environmental_score': {
        'display_name': 'Ethical, Healthy, Environmental',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the ethical, health-conscious, and environmental practices of {company_name} on a scale of 0-10, where:
- 0 = Poor practices, frequent controversies, negative impact on society/environment
- 5 = Standard practices, meets regulatory requirements, moderate commitment to ESG
- 10 = Industry-leading ethical, health, and environmental standards, transformative positive impact

Consider factors like:
- Environmental sustainability and carbon footprint
- Ethical business practices and supply chain transparency
- Health and safety standards for products, employees, and communities
- Commitment to social responsibility and community impact
- Corporate governance and board diversity
- Transparency and reporting on ESG initiatives
- Alignment with global sustainability goals (e.g., UN SDGs)
- Reputation for integrity and social purpose

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'long_term_orientation_score': {
        'display_name': 'Long-term Focus',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the long-term orientation and strategic focus of {company_name} on a scale of 0-10, where:
- 0 = Short-term focused, driven by quarterly results, lack of long-term vision
- 5 = Balanced orientation, meets short-term goals while considering long-term strategy
- 10 = Exceptionally long-term oriented, visionary strategy, willing to sacrifice short-term for long-term value

Consider factors like:
- Investment in R&D and long-term growth initiatives
- Strategic planning cycles and vision (e.g., 5-10+ years)
- Management compensation alignment with long-term performance
- Willingness to make bold, long-term investments even at the expense of short-term earnings
- Focus on sustainable value creation for all stakeholders
- Resistance to short-term market pressures and quarterly-driven decision-making
- Continuity and consistency in strategic direction
- Track record of long-term value creation and transformation

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'execution_ability_score': {
        'display_name': 'Execution Ability',
        'is_reverse': False,
        'weight': 10,
        'max_val': 10,
        'prompt': """Rate the execution ability and operational excellence of {company_name} on a scale of 0-10, where:
- 0 = Poor execution, frequent project delays, operational inefficiencies, inability to meet targets
- 5 = Competent execution, generally meets targets, standard operational performance
- 10 = Exceptional execution, consistently over-delivers, industry-leading operational excellence

Consider factors like:
- Track record of meeting or exceeding financial and strategic targets
- Efficiency and effectiveness of operations and supply chain
- Speed and quality of product/service delivery and innovation
- Ability to manage complex projects and transformations
- Operational agility and resilience in changing environments
- Continuous improvement culture and operational discipline
- Management's ability to execute on its strategic vision
- Reputation for reliability and excellence in execution

Respond with ONLY the numerical score (0-10), no explanation needed."""
    },
    'customer_obsession': {
        'display_name': 'Customer Obsession',
        'is_reverse': False,
        'weight': 1.0,
        'max_val': 100,
        'prompt': """Rate the level of customer obsession at {company_name} on a scale of 0-100, where:
- 0 = Completely company-focused, indifferent to customer needs, poor service
- 50 = Moderate customer focus, standard industry customer service
- 100 = Extremely customer-obsessed, customer needs drive all decisions, legendary service

Consider:
- Customer-centric culture and values
- Investment in customer experience and satisfaction
- Use of customer feedback to drive innovation and improvements
- Responsiveness to customer needs and complaints
- Personalization and tailoring of products/services
- Loyalty and advocacy among customers
- Integration of customer voice into strategic decision-making
- Reputation for going above and beyond for customers

Respond with ONLY the numerical score (0-100), no explanation needed."""
    },
    'adaptability_score': {
        'display_name': 'Adaptability',
        'is_reverse': False,
        'weight': 1.0,
        'max_val': 100,
        'prompt': """Rate the adaptability and agility of {company_name} on a scale of 0-100, where:
- 0 = Rigid, slow to change, stuck in old ways, unable to adapt to market shifts
- 50 = Moderately adaptable, able to make some changes in response to market shifts
- 100 = Extremely adaptable and agile, thrives on change, quickly pivots to new opportunities

Consider:
- Speed of decision-making and execution
- Ability to pivot business models and strategies
- Culture of experimentation and learning from failure
- Resilience in the face of disruption and uncertainty
- Ability to anticipate and respond to changing customer needs and technology trends
- Flexibility in organizational structure and processes
- Track record of successful transformations and adaptations
- Proactive approach to identifying and pursuing new opportunities

Respond with ONLY the numerical score (0-100), no explanation needed."""
    },
    'capital_allocation_score': {
        'display_name': 'Capital Allocation Ability',
        'is_reverse': False,
        'weight': 1.0,
        'max_val': 100,
        'prompt': """Rate the capital allocation ability and financial discipline of {company_name} on a scale of 0-100, where:
- 0 = Poor capital allocation, wasteful spending, low returns on investment, high debt
- 50 = Competent capital allocation, steady returns, standard financial discipline
- 100 = Exceptional capital allocation, high returns on invested capital (ROIC), visionary investment strategy

Consider:
- Return on Invested Capital (ROIC) and other return metrics
- Efficiency and effectiveness of R&D and M&A investments
- Financial discipline and balance sheet strength
- Shareholder-friendly capital return policies (dividends, buybacks)
- Ability to identify and invest in high-return opportunities
- Prudent management of debt and liquidity
- Transparency and accountability in capital allocation decisions
- Track record of value-creating capital allocation over the long term

Respond with ONLY the numerical score (0-100), no explanation needed."""
    }
}

def get_metric_list() -> List[tuple]:
    """Returns metrics in the format used by the app: (key, label, is_reverse, weight)"""
    return [
        (key, d['display_name'], d['is_reverse'], d['weight'])
        for key, d in METRIC_DEFINITIONS.items()
    ]

def calculate_total_weighted_score(scores_dict: Dict[str, Any], selected_keys: List[str] = None) -> float:
    """Calculates total weighted score for a set of metrics. Optimized for performance."""
    if selected_keys is None:
        selected_keys = list(METRIC_DEFINITIONS.keys())
        
    total = 0.0
    # Pre-filter valid keys once
    valid_keys = [k for k in selected_keys if k in METRIC_DEFINITIONS]
    
    # Optimized loop - cache dict lookups
    for key in valid_keys:
        m_def = METRIC_DEFINITIONS[key]
        val = scores_dict.get(key)
        
        if val is None or val == 'N/A':
            continue
            
        try:
            score_value = float(val)
        except (ValueError, TypeError):
            continue
                
        if m_def['is_reverse']:
            total += (m_def['max_val'] - score_value) * m_def['weight']
        else:
            total += score_value * m_def['weight']
            
    return total

def get_max_possible_score(selected_keys: List[str] = None) -> float:
    """Calculates the maximum possible score for a set of metrics."""
    if selected_keys is None:
        selected_keys = list(METRIC_DEFINITIONS.keys())
        
    total_max = 0.0
    for key in selected_keys:
        if key in METRIC_DEFINITIONS:
            m_def = METRIC_DEFINITIONS[key]
            total_max += m_def['max_val'] * m_def['weight']
            
    return total_max
