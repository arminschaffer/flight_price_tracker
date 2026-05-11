from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.services import FlightService
from app.data_manager import data_manager

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def index(): return FileResponse("app/index.html")

@app.get("/routes")
def routes(archived: bool = False):
    return FlightService.get_routes(archived)

@app.get("/dates")
def dates(route: str, archived: bool = False):
    return FlightService.get_dates(route, archived)

@app.get("/line-chart")
def line_chart(route: str, archived: bool = False):
    return FlightService.get_line_chart(route, archived)

@app.get("/heatmap")
def heatmap(route: str, date: str, archived: bool = False):
    return FlightService.get_heatmap(route, date, archived)

@app.get("/table")
def table(route: str, scrape_date: str, dep_date: str, ret_date: str | None = None, archived: bool = False):
    return FlightService.get_table(route, scrape_date, dep_date, ret_date, archived)

@app.get("/refresh")
def refresh():
    data_manager.refresh_data()
    return {"message": "Cache refreshed"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)