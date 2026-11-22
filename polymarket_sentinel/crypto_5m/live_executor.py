"""
Polymarket Real Live CLOB Execution Engine.
Interfaces with official py-clob-client on Polygon (Chain ID 137).
Provides:
1. Wallet verification & USDC.e balance pre-flight check.
2. EIP-712 cryptographic signature derivation.
3. Strict institutional risk guards ($10 max outlay hard cap).
4. Gasless limit/market order placement on Polymarket CLOB.
"""

import os
import time
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("PolymarketLiveExecutor")

CLOB_HOST = "https://clob.polymarket.com"
POLYGON_CHAIN_ID = 137


class PolymarketLiveExecutor:
    def __init__(self):
        self.private_key: Optional[str] = os.getenv("POLYMARKET_PRIVATE_KEY")
        self.funder_address: Optional[str] = os.getenv("POLYMARKET_FUNDER_ADDRESS")
        self.signature_type: int = int(os.getenv("POLYMARKET_SIGNATURE_TYPE", "2" if self.funder_address else "0"))
        self.is_live_enabled: bool = os.getenv("POLYMARKET_LIVE_ENABLED", "false").lower() == "true"
        self.client = None
        self.api_creds = None
        self.wallet_address: Optional[str] = None
        self.last_check_status: Dict[str, Any] = {"connected": False, "reason": "Not initialized"}

        if self.private_key:
            self._init_clob_client()

    @staticmethod
    def _save_to_env(updates: Dict[str, str]):
        """Persists credentials and settings into .env file safely without overwriting other variables."""
        env_path = os.path.join(os.getcwd(), ".env")
        existing_lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                existing_lines = f.readlines()

        keys_updated = set()
        new_lines = []
        for line in existing_lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                k, _ = stripped.split("=", 1)
                k = k.strip()
                if k in updates:
                    new_lines.append(f'{k}="{updates[k]}"\n')
                    keys_updated.add(k)
                    continue
            new_lines.append(line)

        for k, v in updates.items():
            if k not in keys_updated:
                new_lines.append(f'{k}="{v}"\n')

        with open(env_path, "w") as f:
            f.writelines(new_lines)

    def test_connection_creds(self, private_key: str, funder_address: Optional[str] = None, sig_type: Optional[int] = None) -> Dict[str, Any]:
        """Tests live CLOB authentication and checks spendable USDC.e balance & CTF allowance without trading."""
        if not private_key or not private_key.strip():
            return {
                "ok": False,
                "connected": False,
                "reason": "No private key provided."
            }
        try:
            try:
                from py_clob_client_v2 import ClobClient, AssetType, BalanceAllowanceParams
            except ImportError:
                from py_clob_client.client import ClobClient
                from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
            from eth_account import Account

            key = private_key.strip()
            if not key.startswith("0x"):
                key = "0x" + key

            acct = Account.from_key(key)
            wallet_addr = acct.address

            if not funder_address:
                resolved = self.resolve_proxy_wallet(wallet_addr)
                if resolved:
                    funder_address = resolved
                    sig_type = 1

            if sig_type is None:
                sig_type = 2 if funder_address else 0
            funder = funder_address.strip() if funder_address else None

            test_client = ClobClient(
                host=CLOB_HOST,
                chain_id=POLYGON_CHAIN_ID,
                key=key,
                signature_type=sig_type,
                funder=funder
            )
            if hasattr(test_client, "derive_api_key"):
                try:
                    api_creds = test_client.derive_api_key()
                except Exception:
                    api_creds = test_client.create_or_derive_api_key()
            elif hasattr(test_client, "create_or_derive_api_key"):
                api_creds = test_client.create_or_derive_api_key()
            else:
                api_creds = test_client.create_or_derive_api_creds()
            test_client.set_api_creds(api_creds)

            bal_data = test_client.get_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            raw_bal = float(bal_data.get("balance", 0))
            usdc_bal = round(raw_bal / 1e6, 2) if raw_bal > 1000 else round(raw_bal, 2)
            
            allowances_dict = bal_data.get("allowances", {})
            if isinstance(allowances_dict, dict) and allowances_dict:
                allowance = 999999.0
            else:
                raw_allowance = float(bal_data.get("allowance", 0))
                allowance = round(raw_allowance / 1e6, 2) if raw_allowance > 1000 else round(raw_allowance, 2)

            return {
                "ok": True,
                "connected": True,
                "wallet_address": wallet_addr,
                "funder_address": funder,
                "signature_type": sig_type,
                "usdc_balance": usdc_bal,
                "allowance": allowance,
                "message": f"Verified! Live Wallet: {wallet_addr[:6]}...{wallet_addr[-4:]} with ${usdc_bal:.2f} USDC.e available on Polygon."
            }
        except Exception as e:
            return {
                "ok": False,
                "connected": False,
                "reason": str(e)
            }

    def update_credentials(
        self,
        private_key: str,
        funder_address: Optional[str] = None,
        sig_type: Optional[int] = None,
        live_enabled: bool = False,
        persist: bool = True
    ) -> Dict[str, Any]:
        """Validates credentials, updates client in memory, and persists to .env."""
        res = self.test_connection_creds(private_key, funder_address, sig_type)
        if not res.get("ok"):
            return res

        self.private_key = private_key.strip()
        self.funder_address = funder_address.strip() if funder_address else None
        self.is_live_enabled = bool(live_enabled)

        if sig_type is None:
            self.signature_type = 2 if self.funder_address else 0
        else:
            self.signature_type = int(sig_type)

        self._init_clob_client()

        if persist:
            env_updates = {
                "POLYMARKET_PRIVATE_KEY": self.private_key,
                "POLYMARKET_FUNDER_ADDRESS": self.funder_address or "",
                "POLYMARKET_SIGNATURE_TYPE": str(self.signature_type),
                "POLYMARKET_LIVE_ENABLED": "true" if self.is_live_enabled else "false"
            }
            self._save_to_env(env_updates)

        return {
            "ok": True,
            "status": self.get_account_status(),
            "message": "Polymarket credentials verified and saved successfully."
        }

    def set_live_mode(self, enabled: bool) -> Dict[str, Any]:
        """Toggles live real trading vs paper simulation mode."""
        self.is_live_enabled = bool(enabled)
        self._save_to_env({
            "POLYMARKET_LIVE_ENABLED": "true" if self.is_live_enabled else "false"
        })
        return self.get_account_status()

    @staticmethod
    def resolve_proxy_wallet(eoa_address: str) -> Optional[str]:
        """Resolves the user's Polymarket proxy/deposit wallet address via Polymarket Profile API."""
        try:
            import urllib.request
            import ssl
            import json
            url = f"https://polymarket.com/api/profile/userData?address={eoa_address}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, context=ctx, timeout=6) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    proxy = data.get("proxyWallet")
                    if proxy and proxy.startswith("0x"):
                        return proxy.lower()
        except Exception as e:
            logger.warning(f"Could not auto-resolve proxy wallet: {e}")
        return None

    def _init_clob_client(self):
        """Initializes py-clob-client with EIP-712 authentication."""
        try:
            try:
                from py_clob_client_v2 import ClobClient
            except ImportError:
                from py_clob_client.client import ClobClient
            from eth_account import Account

            key = self.private_key.strip()
            if not key.startswith("0x"):
                key = "0x" + key

            acct = Account.from_key(key)
            self.wallet_address = acct.address

            # signature_type: 0 for EOA (MetaMask), 1 or 2 for Polymarket Proxy / Email login
            funder = self.funder_address.strip() if self.funder_address else None
            if not funder:
                resolved = self.resolve_proxy_wallet(self.wallet_address)
                if resolved:
                    self.funder_address = resolved
                    funder = resolved
                    self.signature_type = 1
                    self._save_to_env({
                        "POLYMARKET_FUNDER_ADDRESS": resolved,
                        "POLYMARKET_SIGNATURE_TYPE": "1"
                    })

            sig_type = self.signature_type if self.signature_type is not None else (1 if funder else 0)

            self.client = ClobClient(
                host=CLOB_HOST,
                chain_id=POLYGON_CHAIN_ID,
                key=key,
                signature_type=sig_type,
                funder=funder
            )

            # Derive L2 API credentials
            if hasattr(self.client, "derive_api_key"):
                try:
                    self.api_creds = self.client.derive_api_key()
                except Exception:
                    self.api_creds = self.client.create_or_derive_api_key()
            elif hasattr(self.client, "create_or_derive_api_key"):
                self.api_creds = self.client.create_or_derive_api_key()
            else:
                self.api_creds = self.client.create_or_derive_api_creds()
            self.client.set_api_creds(self.api_creds)

            self.last_check_status = {
                "connected": True,
                "wallet_address": self.wallet_address,
                "funder_address": funder,
                "live_trading_enabled": self.is_live_enabled
            }
        except Exception as e:
            self.last_check_status = {
                "connected": False,
                "reason": str(e)
            }

    def get_account_status(self) -> Dict[str, Any]:
        """Queries Polymarket for real on-chain USDC.e collateral balance & allowances."""
        if not self.client:
            has_key = bool(self.private_key)
            return {
                "configured": has_key,
                "connected": False,
                "wallet_address": self.wallet_address,
                "usdc_balance": 0.0,
                "live_enabled": self.is_live_enabled,
                "reason": "Missing POLYMARKET_PRIVATE_KEY in .env" if not has_key else self.last_check_status.get("reason", "Connection error")
            }

        try:
            try:
                from py_clob_client_v2 import AssetType, BalanceAllowanceParams
            except ImportError:
                from py_clob_client.clob_types import AssetType, BalanceAllowanceParams
            bal_data = self.client.get_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            # USDC.e has 6 decimal places on Polygon
            raw_bal = float(bal_data.get("balance", 0))
            usdc_bal = round(raw_bal / 1e6, 2) if raw_bal > 1000 else round(raw_bal, 2)

            allowances_dict = bal_data.get("allowances", {})
            if isinstance(allowances_dict, dict) and allowances_dict:
                allowance = 999999.0
            else:
                raw_allowance = float(bal_data.get("allowance", 0))
                allowance = round(raw_allowance / 1e6, 2) if raw_allowance > 1000 else round(raw_allowance, 2)

            return {
                "configured": True,
                "connected": True,
                "wallet_address": self.wallet_address,
                "funder_address": self.funder_address,
                "usdc_balance": usdc_bal,
                "allowance": allowance,
                "live_enabled": self.is_live_enabled
            }
        except Exception as e:
            return {
                "configured": True,
                "connected": False,
                "wallet_address": self.wallet_address,
                "usdc_balance": 0.0,
                "live_enabled": self.is_live_enabled,
                "reason": str(e)
            }

    def execute_live_5m_order(
        self,
        token_id: str,
        side: str,
        shares: float,
        price: float,
        max_allowed_ask: float = 0.52
    ) -> Dict[str, Any]:
        """
        Executes a real order on Polymarket CLOB with strict protective risk constraints.
        - Hard Risk Limit: Maximum $10.00 outlay per order.
        - Rejects order if live trading is disabled in .env.
        - Checks CLOB orderbook to match marketable top of book immediately up to max_allowed_ask.
        """
        if not self.is_live_enabled:
            return {
                "ok": False,
                "reason": "Live execution blocked: POLYMARKET_LIVE_ENABLED is false in .env. Switch to true to trade real funds."
            }

        if not self.client:
            return {"ok": False, "reason": "Polymarket client not initialized."}

        # Marketable Immediate-Fill Execution:
        # Cross top of CLOB orderbook up to max_allowed_ask for guaranteed instant fill into Polymarket Positions.
        # If best ask exceeds max_allowed_ask, abort immediately rather than leaving a stranded resting limit bid.
        try:
            ob = self.client.get_order_book(str(token_id))
            if side.upper() == "BUY":
                asks = [float(a["price"]) for a in ob.get("asks", []) if float(a.get("price", 0)) > 0]
                if not asks:
                    return {"ok": False, "reason": "No liquidity in Polymarket CLOB orderbook. Aborted."}
                best_ask = min(asks)
                if best_ask > max_allowed_ask:
                    return {
                        "ok": False,
                        "reason": f"CLOB best ask is {best_ask*100:.0f}¢ (exceeds {max_allowed_ask*100:.0f}¢ ceiling). Aborted to protect risk/reward."
                    }
                price = best_ask
                shares = max(1.0, round(5.0 / price, 1))
            elif side.upper() == "SELL":
                bids = [float(b["price"]) for b in ob.get("bids", []) if float(b.get("price", 0)) > 0]
                if bids:
                    top_bid = max(bids)
                    # If highest bid meets or is within tight slippage (3¢) of target price, match immediately
                    if top_bid >= (price - 0.03):
                        price = top_bid
                    # Otherwise, maintain limit order at target price rather than dumping into predatory lowball bids
        except Exception as ob_err:
            logger.warning(f"Could not inspect live orderbook: {ob_err}")
            if side.upper() == "BUY":
                price = min(max_allowed_ask, max(0.10, price))
                shares = max(1.0, round(5.0 / price, 1))

        outlay = round(shares * price, 2)
        if outlay > 5.50:
            shares = round(5.0 / price, 1)
            outlay = round(shares * price, 2)

        try:
            try:
                from py_clob_client_v2 import OrderArgsV2
                order_args = OrderArgsV2(
                    token_id=str(token_id),
                    price=round(price, 3),
                    size=round(shares, 1),
                    side=side.upper()
                )
            except ImportError:
                from py_clob_client.clob_types import OrderArgs
                order_args = OrderArgs(
                    token_id=str(token_id),
                    price=round(price, 3),
                    size=round(shares, 1),
                    side=side.upper()
                )
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order)

            if isinstance(resp, dict) and resp.get("errorMsg"):
                return {
                    "ok": False,
                    "reason": f"CLOB Rejection: {resp.get('errorMsg')}",
                    "resp": resp
                }

            return {
                "ok": True,
                "order_id": resp.get("orderID") or resp.get("id"),
                "status": resp.get("status", "SUBMITTED"),
                "shares": shares,
                "price": price,
                "outlay": outlay,
                "resp": resp
            }
        except Exception as e:
            return {
                "ok": False,
                "reason": f"CLOB Order Failed: {str(e)}"
            }
