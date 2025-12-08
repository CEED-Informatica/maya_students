from odoo import models, fields, api
from ...support.helper import create_info_register_cancellation

class WizardUpdateRelatedCancellation(models.TransientModel):
  """
  Ventana modal para poder aportar información del resto de anulaciones de un alumno
  """
  _name = "maya_students.wizard_update_related_cancellation"
  _description = "Ventana para poder actualizar anulaciones relacionadas"

  parent_cancellation_id = fields.Many2one(
    "maya_students.cancellation",
    required=True
  )

  line_ids = fields.One2many(
    "maya_students.wizard_update_related_cancellation_line",
    "wizard_id",
    string="Otras anulaciones"
  )

  allow_justification = fields.Boolean(default=lambda self: self.env.context.get("allow_justification", False))

  @api.model
  def default_get(self, fields_list):
    """
    Rellena el wizard con los valores iniciales.
    Se ejecuta antes de cargar el formulario del wizard
    """
    res = super().default_get(fields_list)

    parent_id = self.env.context.get("active_id")
    parent = self.env["maya_students.cancellation"].browse(parent_id)

    res["allow_justification"] = self.env.context.get("allow_justification", False) 
    res["parent_cancellation_id"] = parent.id

    lines = []
    for rel in parent.related_cancellations_ids:
      lines.append((
          0, 0,
          {
              "cancellation_id": rel.id,
              "current_situation": rel.situation,
              "new_situation": False,
              "new_situation_just": False,
          }
      ))

    res["line_ids"] = lines
    return res

  def action_confirm(self):
    """
    Guarda las modificaciones en las anulaciones
    """
    parent_comments = self.parent_cancellation_id.comments
    parent_justification_end_date = self.parent_cancellation_id.justification_end_date

    for line in self.line_ids:
      # Solo actualizamos si realmente ha cambiado algo
      if line.new_situation and line.new_situation != line.cancellation_id.situation:

        comments, _, date = create_info_register_cancellation(self.env.user.maya_employee_id, 
                                                                'AV' if line.new_situation == '6' else 'R2QC', 
                                                                line.cancellation_id.comments_r2) 
        line.cancellation_id.write({
          'situation': line.new_situation,
          'comments_r2': comments,
          'notification_date_r2': date
        })
      elif line.new_situation_just and line.new_situation_just != line.cancellation_id.situation:
        if line.new_situation_just =='6':
          type_cancellation = 'AV'
        elif line.new_situation_just == '5':
          type_cancellation = 'R2QC'
        elif  line.new_situation_just == '7':
          type_cancellation = 'JUS'

        comments, _, date = create_info_register_cancellation(self.env.user.maya_employee_id, 
                                                                type_cancellation, 
                                                                line.cancellation_id.comments_r2) 
      
        # si está justificando → copiar comentarios y fecha
        if line.new_situation_just == '7':
          line.cancellation_id.write({
            'situation': '7',
            'comments_r2': comments,
            'comments': parent_comments,
            'justification_end_date': parent_justification_end_date
          })
        else:
          line.cancellation_id.write({
            'situation': line.new_situation_just,
            'comments_r2': comments,
            'notification_date_r2': date
          })


    return {"type": "ir.actions.act_window_close"}
