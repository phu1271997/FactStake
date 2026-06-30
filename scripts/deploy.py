import os
import sys
import subprocess

def main():
    print("Preparing deployment environment...")
    
    # 1. Verify frontend package dependencies are installed
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))
    if not os.path.exists(os.path.join(frontend_dir, "node_modules")):
        print("Installing frontend npm dependencies...")
        subprocess.run(["npm", "install"], cwd=frontend_dir, check=True)

    # 2. Write the deployment driver in the frontend folder (resolves imports nicely)
    temp_js_path = os.path.join(frontend_dir, "deploy_temp.js")
    
    deploy_js_code = """
import { createClient, createAccount } from 'genlayer-js';
import { simulator } from 'genlayer-js/chains';
import fs from 'fs';

async function main() {
  console.log("Reading contract source files...");
  const reputationCode = fs.readFileSync('../contracts/Reputation.py', 'utf8');
  const marketCode = fs.readFileSync('../contracts/Market.py', 'utf8');
  const factoryCode = fs.readFileSync('../contracts/MarketFactory.py', 'utf8');

  // Use the standard simulator account private key
  const privateKey = process.env.FACTSTAKE_PRIVATE_KEY || '0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7e22d87b90203';
  const account = createAccount(privateKey);
  
  const client = createClient({
    chain: simulator,
    account: account
  });

  console.log("Account Address:", account.address);

  // 1. Deploy Reputation
  console.log("Deploying Reputation contract...");
  await client.initializeConsensusSmartContract();
  const repTx = await client.deployContract({
    code: reputationCode,
    args: []
  });
  const repReceipt = await client.waitForTransactionReceipt({ hash: repTx });
  const repAddress = repReceipt.contractAddress || repReceipt.data?.contract_address;
  console.log("Reputation deployed at:", repAddress);

  // 2. Deploy MarketFactory
  console.log("Deploying MarketFactory contract...");
  await client.initializeConsensusSmartContract();
  const factoryTx = await client.deployContract({
    code: factoryCode,
    args: [marketCode, repAddress]
  });
  const factoryReceipt = await client.waitForTransactionReceipt({ hash: factoryTx });
  const factoryAddress = factoryReceipt.contractAddress || factoryReceipt.data?.contract_address;
  console.log("MarketFactory deployed at:", factoryAddress);
  
  console.log("\\n==================================================");
  console.log("DEPLOYMENT COMPLETED SUCCESSFULLY!");
  console.log("Reputation Address:", repAddress);
  console.log("MarketFactory Address:", factoryAddress);
  console.log("==================================================");
}

main().catch(err => {
  console.error("Deployment failed:", err);
  process.exit(1);
});
"""

    with open(temp_js_path, "w") as f:
        f.write(deploy_js_code)

    print("Running deployment driver via Node...")
    try:
        subprocess.run(["node", "deploy_temp.js"], cwd=frontend_dir, check=True)
    finally:
        # Clean up
        if os.path.exists(temp_js_path):
            os.remove(temp_js_path)

if __name__ == "__main__":
    main()
