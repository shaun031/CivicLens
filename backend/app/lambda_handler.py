from mangum import Mangum

from app.main import app

# Importing this module only constructs an ASGI adapter; it performs no AWS calls.
handler = Mangum(app, lifespan="off")
