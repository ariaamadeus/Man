from django.urls import path
from . import views

app_name = 'tasks'

urlpatterns = [
    path('', views.home, name='home'),
    path('task/add/', views.task_add, name='task_add'),
    path('task/<int:pk>/edit/', views.task_edit, name='task_edit'),
    path('task/<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('task/<int:pk>/toggle-done/', views.task_toggle_done, name='task_toggle_done'),
    path('settings/', views.settings_view, name='settings'),
]
