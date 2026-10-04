from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api import router
from app.config import ROOT
from app.memory import Memory
from app.limits import Admission, BodyLimit

@asynccontextmanager
async def lifespan(app):
    app.state.memory = Memory()
    app.state.busy = set()
    app.state.admission = Admission()
    yield

app = FastAPI(title='TicketPilot | Eraj Zaman i221296', version='1.0.0', lifespan=lifespan)
app.add_middleware(BodyLimit)
app.include_router(router)
app.mount('/static', StaticFiles(directory=ROOT / 'app/static'), name='static')

