"""Proteções aplicadas no runtime, imediatamente antes das ordens de mercado."""
import json
import shutil
import subprocess
import unittest

from app.bridge.js_bridge import CookieClickerBridge


class CaptureBridge(CookieClickerBridge):
    def __init__(self, payload=None):
        self.payload = payload
        self.scripts = []

    def execute_js(self, script):
        self.scripts.append(script)
        return self.payload


def fake_runtime(price=10.0, owned=0, purchase_price=5.0, native_resting=True):
    """Runtime isolado, sem conexão com o jogo ou operações reais."""
    return """
        const good = {id:0, name:'%%1', symbol:'YOU', stock:%s, prev:%s, vals:[10,9]};
        let calls = 0;
        const market = {
            goodsById:[good], brokers:0, ticks:10, tickT:0, secondsPerTick:60, profit:10,
            getGoodPrice:()=>%s, getGoodMaxStock:()=>100,
            buyGood:()=>{calls++; good.stock=100; return true;},
            sellGood:()=>{calls++; good.stock=0; return true;}
        };
        %s
        globalThis.Game = {
            Objects:{Bank:{level:5, minigameLoaded:true, minigame:market}},
            cookiesPsRawHighest:1, cookies:100000, seed:'test', bakeryName:'Biscoitaria',
            HasAchiev:name=>name==='Gaseous assets'
        };
    """ % (
        json.dumps(owned), json.dumps(purchase_price), json.dumps(price),
        "market.getRestingVal=()=>42;" if native_resting else "",
    )


class RuntimeBridge(CookieClickerBridge):
    def __init__(self, runtime):
        self.runtime = runtime
        self.calls = None

    def execute_js(self, script):
        result = subprocess.run(
            [shutil.which("node"), "-e", self.runtime
             + "const result = " + script + "; process.stdout.write(JSON.stringify({result,calls}));"],
            check=True, capture_output=True, text=True,
        )
        payload = json.loads(result.stdout)
        self.calls = payload["calls"]
        return payload["result"]


class StockTradeGuardTests(unittest.TestCase):
    def test_invalid_guards_are_rejected_without_executing_javascript(self):
        invalid_values = (0, -1, float("nan"), float("inf"), True, "10", 10 ** 400)
        for value in invalid_values:
            for method, key in (
                ("buy_stock_max", "price_limit"),
                ("sell_stock_max", "minimum_price"),
                ("sell_stock_max", "expected_purchase_price"),
            ):
                with self.subTest(method=method, key=key, value=value):
                    bridge = CaptureBridge()
                    result = getattr(bridge, method)(0, **{key: value})
                    self.assertFalse(result.success)
                    self.assertEqual(bridge.scripts, [])
        bridge = CaptureBridge()
        self.assertFalse(bridge.buy_stock_max(0, require_empty=1).success)
        self.assertEqual(bridge.scripts, [])

    def test_snapshot_exposes_reference_prices_and_achievement_state(self):
        bridge = CaptureBridge({
            "status": {"available": True, "unlocked": True},
            "bankLevel": 5, "gaseousAssetsWon": True,
            "assets": [{"id": 0, "price": 8, "owned": 0, "restingValue": 14}],
        })
        snapshot = bridge.get_stock_market_snapshot()
        self.assertEqual(snapshot.bank_level, 5)
        self.assertEqual(snapshot.assets[0].resting_value, 14)
        self.assertTrue(snapshot.gaseous_assets_won)

    @unittest.skipUnless(shutil.which("node"), "Node.js indisponível para o runtime JS isolado")
    def test_buy_checks_the_live_price_and_empty_position_before_execution(self):
        for price, owned, should_buy in ((20, 0, False), (21, 0, False), (19, 1, False), (19, 0, True)):
            with self.subTest(price=price, owned=owned):
                bridge = RuntimeBridge(fake_runtime(price=price, owned=owned))
                result = bridge.buy_stock_max(0, price_limit=20, require_empty=True)
                self.assertEqual(result.success, should_buy)
                self.assertEqual(bridge.calls, int(should_buy))

    @unittest.skipUnless(shutil.which("node"), "Node.js indisponível para o runtime JS isolado")
    def test_sale_requires_live_profit_and_the_same_purchase_reference(self):
        for price, purchase, should_sell in ((10, 5, False), (9, 5, False), (11, 6, False), (11, 5, True)):
            with self.subTest(price=price, purchase=purchase):
                bridge = RuntimeBridge(fake_runtime(price=price, owned=100, purchase_price=purchase))
                result = bridge.sell_stock_max(0, minimum_price=10, expected_purchase_price=5)
                self.assertEqual(result.success, should_sell)
                self.assertEqual(bridge.calls, int(should_sell))

    @unittest.skipUnless(shutil.which("node"), "Node.js indisponível para o runtime JS isolado")
    def test_manual_orders_preserve_their_unguarded_behavior(self):
        bridge = RuntimeBridge(fake_runtime(price=1, owned=100, purchase_price=20))
        self.assertTrue(bridge.sell_stock_max(0).success)
        self.assertEqual(bridge.calls, 1)
        bridge = RuntimeBridge(fake_runtime(price=100, owned=1))
        self.assertTrue(bridge.buy_stock_max(0).success)
        self.assertEqual(bridge.calls, 1)

    @unittest.skipUnless(shutil.which("node"), "Node.js indisponível para o runtime JS isolado")
    def test_runtime_reference_price_fallback_and_readable_name(self):
        for native_resting, expected in ((True, 42), (False, 14)):
            with self.subTest(native_resting=native_resting):
                bridge = RuntimeBridge(fake_runtime(native_resting=native_resting))
                snapshot = bridge.get_stock_market_snapshot()
                self.assertEqual(snapshot.assets[0].resting_value, expected)
                self.assertEqual(snapshot.assets[0].name, "Biscoitaria")
                self.assertTrue(snapshot.gaseous_assets_won)


if __name__ == "__main__":
    unittest.main()
