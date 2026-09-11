from dx4000_lcd.screens import ScreenOutput
from dx4000_lcd.renderer import fit_line

class TorrentScreen:
    def render(self, state) -> ScreenOutput:
        if not state.torrent.torrent_name:
            return ScreenOutput(
                line1=fit_line("TOR IDLE"),
                line2=fit_line(f"UP {state.torrent.ul_speed/1024:.1f}K"),
            )
        
        name = state.torrent.torrent_name[:12]
        progress = state.torrent.progress
        return ScreenOutput(
            line1=fit_line(f"TOR {progress:.0f}% {name}"),
            line2=fit_line(f"DL {state.torrent.dl_speed/1024:.1f}K"),
        )
