"""
Wrapper to import the main dashboard app with error handling
"""
import traceback
from shiny import App, ui

try:
    # Use the full dashboard app
    from supabase_shiny import app
except Exception as e:
    error_msg = str(e)
    error_tb = traceback.format_exc()

    error_ui = ui.page_fluid(
        ui.h1("❌ Import Error"),
        ui.h3("Error:"),
        ui.tags.pre(error_msg, style="background: #fee; padding: 10px;"),
        ui.h3("Traceback:"),
        ui.tags.pre(error_tb, style="background: #f5f5f5; padding: 10px; font-size: 11px;")
    )

    def error_server(input, output, session):
        pass

    app = App(error_ui, error_server)
