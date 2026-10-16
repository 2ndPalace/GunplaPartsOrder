"""Order automation module for Bandai Spirits parts ordering website.

This module will be implemented in Phase 2 using Playwright to automate
inputting extracted parts into the Bandai Spirits parts order form.
"""

# フェーズ2（ブラウザ自動化）で実装予定のクラス・関数のスタブ
class BandaiPartsOrderAutomator:
    """Bandai Spirits 部品通販サイトへの自動入力を行うクラス（フェーズ2実装予定）。"""

    def __init__(self, headless: bool = False):
        self.headless = headless

    async def execute_order(self, parts_data: dict) -> None:
        """Playwrightを利用して部品通販サイトにパーツ番号を半自動入力する。"""
        raise NotImplementedError("フェーズ2にて実装予定です。")
