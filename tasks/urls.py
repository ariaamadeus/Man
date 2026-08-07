from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.home, name='home'),
    path('task/add/', views.task_add, name='task_add'),
    path('task/<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('task/<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('task/<int:pk>/toggle-done/', views.task_toggle_done, name='task_toggle_done'),
    path('task/<int:pk>/log-progress/', views.task_log_progress, name='task_log_progress'),
    path('task/<int:pk>/reschedule/', views.task_reschedule, name='task_reschedule'),
    path('settings/', views.settings_view, name='settings'),
    path('google/connect/', views.google_connect, name='google_connect'),
    path('google/callback/', views.google_callback, name='google_callback'),
    path('google/disconnect/', views.google_disconnect, name='google_disconnect'),
    path('google/sync/', views.google_sync_now, name='google_sync_now'),
]
