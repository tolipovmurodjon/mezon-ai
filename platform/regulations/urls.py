from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sorovlar/", views.request_list, name="requests"),
    path("suhbat/", views.ai_chat, name="ai_chat"),
    path("eqaror/", views.eqaror_registry, name="eqaror"),
    path("eqaror/<str:code>/", views.eqaror_detail, name="eqaror_detail"),
    path("eqaror/<str:code>/suhbat/", views.eqaror_chat, name="eqaror_chat"),
    path("eqaror/<str:code>/matn/", views.eqaror_attach, name="eqaror_attach"),
    path("eqaror/<str:code>/agent/", views.eqaror_agent, name="eqaror_agent"),
    path("eqaror/<str:code>/tasdiq/<str:uid>/", views.eqaror_confirm, name="eqaror_confirm"),
    path("suhbat/yuborish/", views.ai_chat_api, name="ai_chat_api"),
    path("sorovlar/yuklash/", views.upload, name="upload"),
    path("havola/", views.eqaror_find, name="eqaror_find"),
    path("tekshiruv/<str:uid>/", views.upload_detail, name="upload_detail"),
    path("tekshiruv/<str:uid>/suhbat/", views.upload_chat, name="upload_chat"),
    path("tekshiruv/<str:uid>/asl.pdf", views.upload_pdf, name="upload_pdf"),
    path("asl/<str:lexid>.pdf", views.original_doc, name="original_doc"),
    path("sorovlar/<int:pk>/", views.review, name="review"),
    path("sorovlar/<int:pk>/tahlil/", views.analyze, name="analyze"),
    path("sorovlar/<int:pk>/suhbat/", views.chat, name="chat"),
    path("sorovlar/<int:pk>/suhbat/tozalash/", views.chat_clear, name="chat_clear"),
    path("sorovlar/<int:pk>/qaror/", views.decide, name="decide"),
    path("hujjatlar/<int:pk>/", views.document_download, name="document_download"),
]
