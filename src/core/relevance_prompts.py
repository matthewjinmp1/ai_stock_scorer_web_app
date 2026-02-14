"""
Single source of truth for relevance scoring prompts used by both:
- scripts/ask_relevance_score.py (single stock: score only; reasoning is the explanation)
- scripts/batch_relevance_scores.py (batch: score only)

Each prompt body uses placeholders {company_name} and {ticker}.
Both programs use the score-only ending; the single script asks the model to reason
and then output only the score (reasoning is shown as the explanation).
"""

# Endings appended to the prompt body depending on which program is calling.
ENDING_SCORE_ONLY = (
    "\n\nReply with only a single number from 0 to 100. No explanation, no other text."
)
# Single script: reason behind the scenes (in thinking); response must be only the score.
ENDING_REASON_THEN_SCORE = (
    "\n\nUse your reasoning (thinking) to analyze step-by-step how the company matches or does not match each part of the description. "
    "Do not put your reasoning, analysis, or explanation in your response. "
    "After reasoning, return only the score: a single number from 0 to 100. Nothing else."
)
ENDING_WITH_EXPLANATION = (
    "\n\nRespond with exactly two lines:\n"
    "1. Score: [number from 0 to 100]\n"
    "2. Explanation: [one or two short sentences explaining why]"
)

# Prompt bodies only (no ending). Keys must match usage in batch (unified cache) and single script.
RELEVANCE_PROMPT_BODIES = [
    {
        "key": "ai",
        "name": "AI Relevance",
        "body": """Rate from 0 to 100 how AI-relevant this company ({company_name}, ticker: {ticker}) is.

Consider:
- How much the company will benefit from the AI revolution
- How involved they are in AI (products, services, R&D, investments)
- How well they are positioned in AI (market position, technology, innovation)
- Overall AI relevance across products, operations, and strategy

Be unbiased. No hype. If a company deserves 0, give 0. If 100, give 100.""",
    },
    {
        "key": "robotics",
        "name": "Robotics Relevance",
        "body": """Rate from 0 to 100 how robotics-relevant this company ({company_name}, ticker: {ticker}) is.

Consider:
- Involvement in robotics (industrial robots, automation, autonomous systems, drones)
- Use of robotics in operations or supply chain
- Products or services that are robotics-related
- R&D or investments in robotics and automation
- Exposure to robotics as a customer or enabler

Be unbiased. No hype. If a company deserves 0, give 0. If 100, give 100.""",
    },
    {
        "key": "disruptive",
        "name": "Disruptive Innovators (ambition/innovation)",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly innovative. Highly ambitious. Disrupts industries rather than waiting to get disrupted. Attracts world class talent. Ambitious and super smart people want to work here. Is not afraid to break the status quo. Executes boldly and rapidly on goals. Thinks long term. Eager to solve customer pains points. Obsessed with the customer. Builds amazing products that people are passionate about. Trailblazer. Disruptive innovator. Sets big goals and executes on them. Always improving. Hungry. Fierce. Bold. Able to adapt rapidly to changing conditions. Desire to make a major impact on the world. It is ok if the company makes mistakes, as long as it gets back up and fights. It is ok if the company is controversial, as long as it keeps fighting and striving.

It does not matter how big the company is, as long as it has these traits.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.""",
    },
    {
        "key": "tech_disruptor_ai",
        "name": "Tech Disruptor / AI Innovator",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly innovative. Highly ambitious. Disrupts industries rather than waiting to get disrupted. Attracts world class talent. Ambitious and super smart people want to work here. Is not afraid to break the status quo. Executes boldly and rapidly on goals. Thinks long term. Builds amazing products that people are passionate about. Trailblazer. Disruptive innovator. Sets big goals and executes on them. Always improving. Hungry. Fierce. Bold. Able to adapt rapidly to changing conditions. Desire to make a major impact on the world. It is ok if the company makes mistakes, as long as it gets back up and fights. It is ok if the company is controversial, as long as it keeps fighting and striving. Takes calculated risks. Hardcore. Intense. Does hard things. Tech company. Software or hardware company. Involved in AI. Integrating AI or supplying to the AI industry.

It does not matter how big the company is, as long as it has these traits.

Focus on the company's current state. Not what they were a long time ago.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.

Be precise too, so don't always say numbers ending in a 5 or 0. You can use the other digits too.""",
    },
    {
        "key": "tech_disruptor_ai_round",
        "name": "Tech Disruptor / AI Innovator (round scores)",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly innovative. Highly ambitious. Disrupts industries rather than waiting to get disrupted. Attracts world class talent. Ambitious and super smart people want to work here. Is not afraid to break the status quo. Executes boldly and rapidly on goals. Thinks long term. Builds amazing products that people are passionate about. Trailblazer. Disruptive innovator. Sets big goals and executes on them. Always improving. Hungry. Fierce. Bold. Able to adapt rapidly to changing conditions. Desire to make a major impact on the world. It is ok if the company makes mistakes, as long as it gets back up and fights. It is ok if the company is controversial, as long as it keeps fighting and striving. Takes calculated risks. Hardcore. Intense. Does hard things. Tech company. Software or hardware company. Involved in AI. Integrating AI or supplying to the AI industry.

It does not matter how big the company is, as long as it has these traits.

Focus on the company's current state. Not what they were a long time ago.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.""",
    },
    {
        "key": "tech_disruptor_ai_round_score_only",
        "name": "Tech Disruptor / AI Innovator (reason, score only in final answer)",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly innovative. Highly ambitious. Disrupts industries rather than waiting to get disrupted. Attracts world class talent. Ambitious and super smart people want to work here. Is not afraid to break the status quo. Executes boldly and rapidly on goals. Thinks long term. Builds amazing products that people are passionate about. Trailblazer. Disruptive innovator. Sets big goals and executes on them. Always improving. Hungry. Fierce. Bold. Able to adapt rapidly to changing conditions. Desire to make a major impact on the world. It is ok if the company makes mistakes, as long as it gets back up and fights. It is ok if the company is controversial, as long as it keeps fighting and striving. Takes calculated risks. Hardcore. Intense. Does hard things. Tech company. Software or hardware company. Involved in AI. Integrating AI or supplying to the AI industry.

It does not matter how big the company is, as long as it has these traits.

Focus on the company's current state. Not what they were a long time ago.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.""",
        "single_score_only": True,
    },
    {
        "key": "tandem_company",
        "name": "Tandem Company",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Highly consistent. Mathematically disciplined. Dominates niches rather than chasing trends. Generates cash flow in any economy. Boring and super profitable. Is not afraid to be boring. Compounds wealth slowly and surely. Thinks in decades. Builds essential services that people cannot live without. Tollbooth. Economic inevitability. Sets dividend goals and hits them every year. Always compounding. Steady. Reliable. Unshakeable. Able to weather any storm without blinking. Desire to protect capital while growing it. It is not ok to cut the dividend. It is ok if the stock moves slowly, as long as it keeps paying and growing. Takes zero unnecessary risks. Disciplined. Focused. Does simple things perfectly. Essential service. Infrastructure or payment rail. Involved in the plumbing of the economy. Monetizing every transaction.

It does not matter how big the company is, as long as it has these traits.

Focus on the company's current state. Not what they were a long time ago.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.""",
    },
    {
        "key": "all_weather",
        "name": "All-Weather Company",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

"All-weather" companies. Consistent, repeatable investment experience. Low volatility. Consistent Fundamental Growth: sustained growth in revenue, earnings, and cash flow through any economic environment, not just during expansions. Competitive Advantage: distinct "moat," dominance, or uniqueness that insulates them from competition. Management Stability: depth and consistency in the executive team. Avoid companies with frequent leadership turnover. Avoid "turnaround stories" or speculative high-growth stocks. Proven, high-quality businesses that offer predictable performance and downside protection.

It does not matter how big the company is, as long as it has these traits.

Focus on the company's current state. Not what they were a long time ago.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.""",
    },
    {
        "key": "durable_advantage",
        "name": "The Buffett",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

This is a stock that Warren Buffett would invest in.

It does not matter how big the company is, as long as it has these traits.

Focus on the company's current state. Not what they were a long time ago.

Be radically unbiased. No hype. If a company deserves a 0, give it a 0. If a company deserves a 100, give it a 100.""",
    },
    {
        "key": "ai_disruption_risk",
        "name": "AI Disruption Risk",
        "body": """Rate from 0 to 100 how well this company ({company_name}, ticker: {ticker}) matches this description:

Their current business model is at risk of getting disrupted by AI. Industry is at risk of being disrupted by AI. Or they are currently in the process of being disrupted by AI.""",
    },
]


def get_prompt(key: str, with_explanation: bool, company_name: str = "", ticker: str = "") -> str:
    """Return the full prompt for a given key, with placeholders filled and the appropriate ending.

    - with_explanation=True: for single-stock script (score + explanation).
    - with_explanation=False: for batch script (score only).
    """
    for p in RELEVANCE_PROMPT_BODIES:
        if p["key"] == key:
            body = p["body"].format(company_name=company_name or "{company_name}", ticker=ticker or "{ticker}")
            ending = ENDING_WITH_EXPLANATION if with_explanation else ENDING_SCORE_ONLY
            return body + ending
    raise KeyError(f"Unknown relevance prompt key: {key}")


def get_prompt_template(key: str, with_explanation: bool) -> str:
    """Return the full prompt template string (with {company_name} and {ticker}) for a given key."""
    for p in RELEVANCE_PROMPT_BODIES:
        if p["key"] == key:
            return p["body"] + (ENDING_WITH_EXPLANATION if with_explanation else ENDING_SCORE_ONLY)
    raise KeyError(f"Unknown relevance prompt key: {key}")


def build_prompts_for_batch():
    """Return list of {key, name, prompt} for batch_relevance_scores (score-only ending, plus reason-then-score variant)."""
    result = [
        {"key": p["key"], "name": p["name"], "prompt": p["body"] + ENDING_SCORE_ONLY}
        for p in RELEVANCE_PROMPT_BODIES
    ]
    # Add "reason, score only in final answer" variant for Tech Disruptor (same body, reason-then-score ending)
    for p in RELEVANCE_PROMPT_BODIES:
        if p.get("single_score_only"):
            result.append({
                "key": "tech_disruptor_ai_round_reason_then_score",
                "name": "Tech Disruptor / AI Innovator (reason, score only in final answer)",
                "prompt": p["body"] + ENDING_REASON_THEN_SCORE,
            })
            break
    return result


def build_prompts_for_single():
    """Return list of {key, name, prompt, score_only_no_reasoning?} for ask_relevance_score.
    score_only prompts still ask to reason; they just require only the score in the final answer.
    """
    result = []
    for p in RELEVANCE_PROMPT_BODIES:
        # All single prompts ask to reason then give score; score_only is for display/attribution only.
        prompt = p["body"] + ENDING_REASON_THEN_SCORE
        result.append({
            "key": p["key"],
            "name": p["name"],
            "prompt": prompt,
            "score_only_no_reasoning": bool(p.get("single_score_only")),
        })
    return result
