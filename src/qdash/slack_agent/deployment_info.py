#!/usr/bin/env python3
"""
Get detailed deployment information from Prefect server.
"""
import asyncio

from prefect.client.orchestration import PrefectClient


async def get_deployment_details():
    """Get detailed deployment information."""
    client = PrefectClient(api="http://prefect-server:4200/api")
    
    try:
        deployments = await client.read_deployments()
        print(f"📋 Found {len(deployments)} deployments:\n")
        
        for dep in deployments:
            print(f"Name: {dep.name}")
            print(f"Flow Name: {dep.flow_name}")  
            print(f"Full Format: {dep.flow_name}/{dep.name}")
            print(f"ID: {dep.id}")
            print(f"Description: {dep.description}")
            print(f"Parameters: {dep.parameters}")
            print("-" * 60)
            
        # Try to find chip report specifically
        chip_reports = [d for d in deployments if "chip" in d.name.lower() and "report" in d.name.lower()]
        if chip_reports:
            print("\n🎯 Chip Report Deployments:")
            for dep in chip_reports:
                correct_name = f"{dep.flow_name}/{dep.name}"
                print(f"  Correct format: {correct_name}")
                
                # Test this format
                try:
                    await client.read_deployment_by_name(correct_name)
                    print(f"  ✅ Format works: {correct_name}")
                except Exception as e:
                    print(f"  ❌ Format failed: {e}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(get_deployment_details())