"""
Mock forecast API endpoints for EFM chatbot development.
Simulates SAP HANA forecast data responses.
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.services.mock_forecast import mock_forecast_service
from app.auth.ctx import must_get_auth_ctx, AuthCtx, Metadata

forecast_router = APIRouter(prefix="/forecast", tags=["forecast"])


@forecast_router.get("/summary")
async def get_forecast_summary(
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> JSONResponse:
    """
    Get forecast summary with top account and product variances.
    This endpoint simulates what would be a call to SAP HANA.
    """
    try:
        user_id = auth_ctx.user.id
        user_role = "analyst"  # Default role for mock data
        
        summary_data = await mock_forecast_service.get_forecast_summary(
            user_id=user_id, 
            user_role=user_role
        )
        
        return JSONResponse(content=summary_data)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch forecast summary: {str(e)}")


@forecast_router.get("/account/{account_name}/variance")
async def get_account_variance(
    account_name: str,
    period: str = "current",
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> JSONResponse:
    """
    Get detailed variance information for a specific account.
    """
    try:
        variance_data = await mock_forecast_service.get_account_variance_details(
            account_name=account_name,
            period=period
        )
        
        return JSONResponse(content=variance_data)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch account variance: {str(e)}")


@forecast_router.get("/product/{product_name}/impact")
async def get_product_impact(
    product_name: str,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> JSONResponse:
    """
    Analyze the impact of a specific product across accounts.
    """
    try:
        impact_data = await mock_forecast_service.get_product_impact_analysis(
            product_name=product_name
        )
        
        return JSONResponse(content=impact_data)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch product impact: {str(e)}")


@forecast_router.get("/conversations/search")
async def search_conversations(
    query: str,
    limit: int = 10,
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> JSONResponse:
    """
    Search through previous forecast conversations for RAG functionality.
    """
    try:
        conversation_data = await mock_forecast_service.search_forecast_conversations(
            query=query,
            limit=limit
        )
        
        return JSONResponse(content={
            "query": query,
            "results": conversation_data,
            "total_found": len(conversation_data)
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to search conversations: {str(e)}")


@forecast_router.get("/permissions")
async def get_user_permissions(
    auth_ctx: AuthCtx[Metadata] = Depends(must_get_auth_ctx)
) -> JSONResponse:
    """
    Get user permissions and data access scope.
    """
    try:
        user_id = auth_ctx.user.id
        permissions = await mock_forecast_service.get_user_permissions(user_id)
        
        return JSONResponse(content=permissions)
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch user permissions: {str(e)}")
