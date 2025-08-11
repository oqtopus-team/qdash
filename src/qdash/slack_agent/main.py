#!/usr/bin/env python3.10
"""
Main entry point for the QDash Strands Slack Agent.
This is the primary Slack agent implementation using Strands Agents SDK.
"""

import asyncio
import logging

from qdash.slack_agent.agent import main

if __name__ == "__main__":
    logging.info("🚀 Starting QDash Strands Slack Agent...")
    asyncio.run(main())
