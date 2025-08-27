"""Mock forecast service to simulate SAP HANA responses for EFM chatbot development."""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import random


class MockForecastService:
    """Mock service that provides sample forecast data for testing and development."""
    
    def __init__(self):
        """Initialize with sample data."""
        self.sample_accounts = [
            "NVIDIA Corporation - North America",
            "Tesla Motors Inc - Global",
            "Apple Inc - Consumer Division", 
            "Microsoft Corporation - Enterprise",
            "Google LLC - Cloud Services",
            "Amazon Web Services - Infrastructure",
            "Meta Platforms - Advertising",
            "Oracle Corporation - Database Solutions"
        ]
        
        self.sample_products = [
            "GPU H100 Series",
            "GPU A100 Series", 
            "GPU RTX 4090",
            "Data Center Solutions",
            "Automotive AI Platforms",
            "Edge Computing Modules",
            "Professional Workstations",
            "Gaming Graphics Cards"
        ]
        
    async def get_forecast_summary(self, user_id: str, user_role: str = "analyst") -> Dict[str, Any]:
        """
        Get forecast summary with top accounts and products showing variances.
        
        Args:
            user_id: User requesting the data
            user_role: User's role for filtering data access
            
        Returns:
            Dictionary containing forecast summary data
        """
        current_month = datetime.now().strftime("%B %Y")
        previous_month = (datetime.now() - timedelta(days=30)).strftime("%B %Y")
        
        return {
            "period": {
                "current": current_month,
                "previous": previous_month
            },
            "top_accounts_with_variances": [
                {
                    "account_name": account,
                    "current_forecast": random.randint(50000, 500000) * 1000,
                    "previous_forecast": random.randint(40000, 450000) * 1000,
                    "variance_amount": random.randint(-50000, 100000) * 1000,
                    "variance_percentage": round(random.uniform(-15.5, 25.8), 1),
                    "primary_driver": random.choice(self.sample_products)
                }
                for account in self.sample_accounts[:5]
            ],
            "top_products_causing_variances": [
                {
                    "product_name": product,
                    "total_variance": random.randint(-30000, 80000) * 1000,
                    "affected_accounts": random.randint(3, 8),
                    "variance_percentage": round(random.uniform(-12.3, 28.7), 1),
                    "trend": random.choice(["increasing", "decreasing", "stable"])
                }
                for product in self.sample_products[:6]
            ],
            "summary_metrics": {
                "total_forecast_current": random.randint(800000, 1200000) * 1000,
                "total_forecast_previous": random.randint(750000, 1100000) * 1000,
                "overall_variance": random.randint(-50000, 150000) * 1000,
                "accounts_with_increases": random.randint(15, 25),
                "accounts_with_decreases": random.randint(8, 18),
                "products_driving_growth": random.randint(4, 8)
            },
            "user_context": {
                "user_id": user_id,
                "role": user_role,
                "accessible_regions": ["North America", "EMEA", "APAC"] if user_role == "global_analyst" else ["North America"],
                "last_updated": datetime.now().isoformat()
            }
        }
    
    async def get_account_variance_details(self, account_name: str, period: str = "current") -> Dict[str, Any]:
        """
        Get detailed variance information for a specific account.
        
        Args:
            account_name: Name of the account to analyze
            period: Time period for analysis
            
        Returns:
            Detailed account variance data
        """
        return {
            "account_name": account_name,
            "period": period,
            "variance_breakdown": [
                {
                    "product": product,
                    "current_forecast": random.randint(10000, 100000) * 1000,
                    "previous_forecast": random.randint(8000, 95000) * 1000,
                    "variance": random.randint(-15000, 25000) * 1000,
                    "reason": random.choice([
                        "Market expansion in new territories",
                        "Increased demand for AI workloads", 
                        "Customer infrastructure upgrade cycle",
                        "Competitive pricing pressure",
                        "Supply chain optimization",
                        "New product line introduction"
                    ])
                }
                for product in random.sample(self.sample_products, 4)
            ],
            "historical_trends": [
                {
                    "month": (datetime.now() - timedelta(days=30*i)).strftime("%Y-%m"),
                    "forecast_value": random.randint(80000, 120000) * 1000,
                    "actual_value": random.randint(75000, 115000) * 1000 if i > 0 else None
                }
                for i in range(6)
            ]
        }
    
    async def get_product_impact_analysis(self, product_name: str) -> Dict[str, Any]:
        """
        Analyze the impact of a specific product across accounts.
        
        Args:
            product_name: Name of the product to analyze
            
        Returns:
            Product impact analysis data
        """
        return {
            "product_name": product_name,
            "total_forecast_impact": random.randint(100000, 300000) * 1000,
            "accounts_affected": [
                {
                    "account_name": account,
                    "forecast_contribution": random.randint(20000, 80000) * 1000,
                    "variance_from_plan": random.randint(-10000, 20000) * 1000,
                    "confidence_level": random.choice(["High", "Medium", "Low"])
                }
                for account in random.sample(self.sample_accounts, 5)
            ],
            "market_factors": [
                "AI/ML workload acceleration driving demand",
                "Data center modernization trends",
                "Cloud migration initiatives",
                "Gaming and content creation growth",
                "Autonomous vehicle development"
            ][:random.randint(2, 5)],
            "risk_factors": [
                "Supply chain constraints",
                "Competitive product launches", 
                "Economic uncertainty in key markets",
                "Regulatory changes in target regions"
            ][:random.randint(1, 3)]
        }
    
    async def search_forecast_conversations(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Mock search through previous forecast conversations for RAG functionality.
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of similar past conversations
        """
        sample_conversations = [
            {
                "conversation_id": f"conv_{i}",
                "user_query": f"What's driving the forecast variance in {random.choice(self.sample_accounts)}?",
                "agent_response": f"The primary driver is {random.choice(self.sample_products)} with increased demand from market expansion.",
                "timestamp": (datetime.now() - timedelta(days=random.randint(1, 30))).isoformat(),
                "relevance_score": round(random.uniform(0.6, 0.95), 2),
                "context_tags": ["variance_analysis", "account_deep_dive", "product_impact"]
            }
            for i in range(min(limit, 15))
        ]
        
        # Sort by relevance score
        return sorted(sample_conversations, key=lambda x: x["relevance_score"], reverse=True)[:limit]
    
    async def get_user_permissions(self, user_id: str) -> Dict[str, Any]:
        """
        Get user permissions and data access scope.
        
        Args:
            user_id: User identifier
            
        Returns:
            User permissions and access scope
        """
        # Mock different user roles
        roles = {
            "global_analyst": {
                "regions": ["North America", "EMEA", "APAC"],
                "accounts": "all",
                "products": "all",
                "can_view_actuals": True
            },
            "regional_manager": {
                "regions": ["North America"],
                "accounts": self.sample_accounts[:4],
                "products": "all",
                "can_view_actuals": True
            },
            "account_manager": {
                "regions": ["North America"],
                "accounts": self.sample_accounts[:2],
                "products": self.sample_products[:5],
                "can_view_actuals": False
            }
        }
        
        # Randomly assign a role for demo purposes
        assigned_role = random.choice(list(roles.keys()))
        
        return {
            "user_id": user_id,
            "role": assigned_role,
            "permissions": roles[assigned_role],
            "last_login": datetime.now().isoformat(),
            "data_freshness": datetime.now().isoformat()
        }


# Global instance for use in the application
mock_forecast_service = MockForecastService()
