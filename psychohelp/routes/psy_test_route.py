from fastapi import HTTPException, Request

from psychohelp.routes.upload_limits import PsyTestImageUploadRoute
from psychohelp.services.psy_test_exceptions import PsyTestInvalidAnswer, PsyTestNotFound, PsyTestStateConflict


class PsyTestRoute(PsyTestImageUploadRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request):
            try:
                return await handler(request)
            except PsyTestNotFound as exc:
                raise HTTPException(404, str(exc)) from exc
            except PsyTestStateConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            except PsyTestInvalidAnswer as exc:
                raise HTTPException(422, str(exc)) from exc

        return handle
