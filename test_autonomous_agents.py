#!/usr/bin/env python3
"""
Test script for autonomous agent system.

Tests:
1. Single agent execution
2. Multi-agent parallel execution
3. Approval workflow
"""
import asyncio
import sys
from app.agent.orchestrator import (
    AgentRole,
    run_agent,
    run_autonomous_cycle,
)


async def test_single_agent():
    """Test running a single agent."""
    print("\n" + "=" * 60)
    print("TEST 1: Single Agent Execution (Job Hunter)")
    print("=" * 60)

    result = await run_agent(
        role=AgentRole.JOB_HUNTER,
        task="Find 3 high-paying Python freelance jobs on Upwork",
        auto_approve_low_risk=True
    )

    print(f"\nStatus: {result.get('status')}")

    if result.get('status') == 'completed':
        print(f"Response: {result.get('response', '')[:500]}...")
        print(f"Tools executed: {result.get('tools_executed', 0)}")
    elif result.get('status') == 'pending_approval':
        print(f"Approval ID: {result.get('approval_id')}")
        print(f"Tools proposed: {result.get('tools_proposed')}")
        for tool in result.get('tool_details', []):
            print(f"  - {tool['name']}: {tool['risk']} risk")
    else:
        print(f"Error: {result.get('error')}")

    return result


async def test_multi_agent():
    """Test running multiple agents in parallel."""
    print("\n" + "=" * 60)
    print("TEST 2: Multi-Agent Parallel Execution")
    print("=" * 60)

    agents = [
        AgentRole.JOB_HUNTER,
        AgentRole.RESEARCHER,
    ]

    print(f"\nRunning {len(agents)} agents: {[a.value for a in agents]}")

    result = await run_autonomous_cycle(
        agents=agents,
        auto_approve_low_risk=True
    )

    print(f"\nCompleted: {len(result['completed'])}")
    print(f"Pending approvals: {len(result['pending_approvals'])}")
    print(f"Errors: {len(result['errors'])}")

    # Show completed agent summaries
    for completed in result['completed']:
        print(f"\n✓ {completed['agent']}:")
        print(f"  {completed['response'][:200]}...")
        print(f"  Tools executed: {completed['tools_executed']}")

    # Show pending approvals
    for pending in result['pending_approvals']:
        print(f"\n⏳ {pending['role']} (pending approval):")
        print(f"  Approval ID: {pending['approval_id']}")
        print(f"  Tools proposed: {pending['tools_proposed']}")

    # Show errors
    for error in result['errors']:
        print(f"\n❌ {error['agent']}:")
        print(f"  Error: {error.get('error', 'Unknown error')}")

    return result


async def main():
    """Run all tests."""
    print("🚀 AUTONOMOUS AGENT SYSTEM TEST")
    print("=" * 60)

    # Check if ANTHROPIC_API_KEY is set
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("❌ ERROR: ANTHROPIC_API_KEY environment variable not set")
        print("Please set it with: export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)

    print("✓ ANTHROPIC_API_KEY is set")

    try:
        # Test 1: Single agent
        await test_single_agent()

        # Test 2: Multi-agent
        await test_multi_agent()

        print("\n" + "=" * 60)
        print("✅ ALL TESTS COMPLETED")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ TEST FAILED: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
