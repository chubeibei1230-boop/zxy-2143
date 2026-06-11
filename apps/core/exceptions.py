from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        return Response({
            'code': response.status_code,
            'message': response.data.get('detail', str(exc)),
            'data': None,
        }, status=response.status_code)

    return Response({
        'code': status.HTTP_500_INTERNAL_SERVER_ERROR,
        'message': str(exc),
        'data': None,
    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class APIResponse(Response):
    def __init__(self, data=None, message='success', code=0, status_code=None, **kwargs):
        response_data = {
            'code': code,
            'message': message,
            'data': data,
        }
        super().__init__(response_data, status=status_code or status.HTTP_200_OK, **kwargs)
