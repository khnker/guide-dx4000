from dx4000_lcd.screens import ScreenOutput
from dx4000_lcd.renderer import fit_line
from dx4000_lcd.formatters import format_bytes, format_percent

class StorageScreen:
    def render(self, state) -> ScreenOutput:
        pct = state.storage.used_pct
        total_tb = state.storage.total_bytes / (1024 ** 4)
        used_tb = state.storage.used_bytes / (1024 ** 4)
        
        # Generar barra usando cgram slots 0-3
        from dx4000_lcd.bar import render_bar
        bar = "".join(render_bar(pct, 7))
        
        return ScreenOutput(
            line1=fit_line(f"STO {bar} {round(pct)}%"),
            line2=fit_line(f"{used_tb:.1f}T/{total_tb:.1f}T FREE"),
        )
