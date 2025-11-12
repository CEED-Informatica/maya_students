# -*- coding: utf-8 -*-

from odoo import api, models, fields

class NotificationGroup(models.Model):
  """
  Hereda de maya_core.notification_provider para sobreescribior la funcion que 
  genera la parte correspondiente de la notificación 
  """

  _inherit = "maya_core.notification_group"

  def render_block(self, user, group) -> str:
    """
    Genera el bloque HTML a insertar en la notificación
    Sobreeescribe el método del modelo padre

    :user Usuario odoo al que hay que notificar
    :group Grupo de notificaciones del proveedor actual sobre el que se renderizan
           las notificaciones
    
    :return HTML listo para insertar.
    """  

    provider = self.env.ref('maya_students.notification_provider')  
    
    notifications = self.env['maya_core.notification_item'].search([
        ('user_id', '=', user.id),
        ('provider_id', '=', provider.id),
        ('ngroup_id', '=', group.id)
    ])   

    if not notifications:
      return ""
    
    if group.id == self.env.ref('maya_students.notification_group_exofficio_cancellations').id:
      template = "maya_students.notification_cancellation_teacher_task"
    else:  
      print('No se encuentra el grupo')
      return ""

    return self.env['ir.ui.view']._render_template(
      template,{
        "notifications": notifications,
    })