"""
Singleton Pattern Example for AsterPublicClient

This example demonstrates the singleton pattern implementation:
- Only one instance per base_url is created
- Multiple calls to AsterPublicClient() return the same instance
- Cache is shared across all references to the same instance
- Different base_urls create separate singleton instances

This ensures efficient memory usage and prevents duplicate cache data.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import aster_client
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aster_client.public_client import AsterPublicClient


async def main():
    """Demonstrate singleton pattern behavior."""
    
    print("=" * 70)
    print("🔹 SINGLETON PATTERN DEMONSTRATION")
    print("=" * 70)
    
    # Example 1: Multiple instances with same URL
    print("\n📝 Example 1: Creating multiple instances with same base_url")
    print("-" * 70)
    
    client1 = AsterPublicClient()
    client2 = AsterPublicClient()
    client3 = AsterPublicClient()
    
    print(f"client1 ID: {id(client1)}")
    print(f"client2 ID: {id(client2)}")
    print(f"client3 ID: {id(client3)}")
    
    if client1 is client2 is client3:
        print("✅ All three variables point to the SAME instance (Singleton)")
    else:
        print("❌ Different instances created (Not a singleton)")
    
    # Example 2: Cache sharing
    print("\n📝 Example 2: Cache is shared across all references")
    print("-" * 70)
    
    async with client1:
        # client1 warms up cache
        pass  # auto_warmup is enabled by default
    
    cache_size_1 = len(client1._symbol_info_cache)
    cache_size_2 = len(client2._symbol_info_cache)
    cache_size_3 = len(client3._symbol_info_cache)
    
    print(f"client1 cache size: {cache_size_1}")
    print(f"client2 cache size: {cache_size_2}")
    print(f"client3 cache size: {cache_size_3}")
    
    if cache_size_1 == cache_size_2 == cache_size_3:
        print("✅ All references share the same cache")
    else:
        print("❌ Caches are different")
    
    # Example 3: Different base_url creates different instance
    print("\n📝 Example 3: Different base_url creates separate singleton")
    print("-" * 70)
    
    client_mainnet = AsterPublicClient("https://fapi.asterdex.com")
    client_testnet = AsterPublicClient("https://testnet.asterdex.com")
    
    print(f"Mainnet client ID: {id(client_mainnet)}")
    print(f"Testnet client ID: {id(client_testnet)}")
    
    if client_mainnet is not client_testnet:
        print("✅ Different base_urls create separate singleton instances")
    else:
        print("❌ Same instance for different URLs")
    
    # Example 4: Show all singleton instances
    print("\n📝 Example 4: View all singleton instances")
    print("-" * 70)
    
    print(f"Total singleton instances: {len(AsterPublicClient._instances)}")
    for url in AsterPublicClient._instances.keys():
        print(f"  - {url}")
    
    # Example 5: Memory efficiency
    print("\n📝 Example 5: Memory efficiency benefits")
    print("-" * 70)
    
    # Create many "instances" - they all point to the same object
    clients = [AsterPublicClient() for _ in range(100)]
    unique_ids = len(set(id(c) for c in clients))
    
    print(f"Created 100 'instances' of AsterPublicClient")
    print(f"Unique object IDs: {unique_ids}")
    
    if unique_ids == 1:
        print("✅ Only 1 actual instance in memory (Singleton working!)")
        print("   This saves memory and ensures cache consistency")
    else:
        print(f"❌ {unique_ids} different instances created")
    
    # Cleanup
    await client_mainnet.close()
    await client_testnet.close()
    
    print("\n" + "=" * 70)
    print("✨ Singleton pattern demonstration complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
