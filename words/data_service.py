from django.db import models, transaction
from django.core.cache import cache
import json
import logging
import uuid
from datetime import datetime
import traceback
from django.db.models import Model
from django.db.models.query import QuerySet

logger = logging.getLogger(__name__)

# Custom JSON encoder to handle Django model instances
class DjangoJSONEncoder(json.JSONEncoder):
    """
    JSONEncoder subclass that knows how to encode Django models and querysets.
    """
    def default(self, obj):
        # Handle Django model instances
        if isinstance(obj, Model):
            return {'_model_id': obj.id, '_model_class': obj.__class__.__name__}
        # Handle Django querysets
        elif isinstance(obj, QuerySet):
            return list(obj)
        # Handle datetime objects
        elif isinstance(obj, datetime):
            return obj.isoformat()
        # Let the base class handle anything else
        return super().default(obj)

class DataService:
    """
    Service for handling data operations with undo functionality.
    This class provides methods for deleting data from models and restoring deleted data.
    """
    
    @staticmethod
    def _serialize_model_instance(instance):
        """
        Serialize a model instance to a dictionary.
        """
        data = {}
        for field in instance._meta.fields:
            field_name = field.name
            if field_name != 'id' and not field_name.endswith('_id'):
                value = getattr(instance, field_name)
                # Handle datetime objects
                if isinstance(value, datetime):
                    value = value.isoformat()
                # Skip Django model instances (handled by custom encoder)
                elif isinstance(value, Model):
                    continue
                data[field_name] = value
        # Add id for all instances (needed for relationships)
        data['id'] = instance.id
        return data
    
    @staticmethod
    def _get_related_models(model):
        """
        Get all models with foreign keys to the given model.
        """
        related_models = []
        for related_object in model._meta.related_objects:
            if isinstance(related_object, models.fields.related.ForeignObjectRel):
                related_models.append(related_object.related_model)
        return related_models
    
    @staticmethod
    def _get_parent_models(model):
        """
        Get all models that this model has foreign keys to.
        """
        parent_models = []
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey):
                parent_models.append((field.related_model, field.name))
        return parent_models
    
    @classmethod
    def delete_by_id(cls, model_class, id_value):
        """
        Delete a record by ID and cache it for potential restoration.
        Returns a tuple of (success, message)
        """
        try:
            with transaction.atomic():
                # Get the instance
                instance = model_class.objects.get(id=id_value)
                instance_id = instance.id  # Store ID separately
                
                # Initialize deleted data structure
                deleted_data = {
                    'model': model_class.__name__,
                    'data': cls._serialize_model_instance(instance),
                    'related_data': {},
                    'parent_data': {},
                    'manually_deleted_examples': []  # Track manually deleted examples
                }
                
                # Special handling to track manually deleted examples for FrenchWord
                if model_class.__name__ == 'FrenchWord':
                    from django.apps import apps
                    FrenchExample = apps.get_model('words', 'FrenchExample')
                    related_examples = FrenchExample.objects.filter(french_word_id=instance_id)
                    
                    # If there are examples, store them for restoration
                    if related_examples.exists():
                        for example in related_examples:
                            example_data = cls._serialize_model_instance(example)
                            deleted_data['manually_deleted_examples'].append({
                                'model': 'FrenchExample',
                                'data': example_data,
                                'french_word_id': instance_id
                            })
                        logger.info(f"Tracked {related_examples.count()} manually deleted examples for FrenchWord {instance_id}")
                
                # Get all child models (models that have foreign keys to this model)
                related_models = cls._get_related_models(model_class)
                
                # For each child model, find and store instances related to our instance
                for related_model in related_models:
                    # Get the field name in the related model that points to our model
                    for field in related_model._meta.fields:
                        if isinstance(field, models.ForeignKey) and field.related_model == model_class:
                            related_field_name = field.name
                            # Use ID for filtering instead of instance object
                            filter_kwargs = {f"{related_field_name}_id": instance_id}
                            related_instances = related_model.objects.filter(**filter_kwargs)
                            
                            # Store related instances
                            if related_instances.exists():
                                deleted_data['related_data'][related_model.__name__] = {
                                    'field_name': related_field_name,
                                    'instances': [cls._serialize_model_instance(rel_instance) for rel_instance in related_instances]
                                }
                
                # Get all parent models (models this model has foreign keys to)
                parent_models = cls._get_parent_models(model_class)
                
                # Store parent references
                for parent_model, field_name in parent_models:
                    parent_id = getattr(instance, f"{field_name}_id")
                    if parent_id:
                        try:
                            parent_instance = parent_model.objects.get(id=parent_id)
                            deleted_data['parent_data'][parent_model.__name__] = {
                                'field_name': field_name,
                                'id': parent_id,
                                'data': cls._serialize_model_instance(parent_instance)
                            }
                        except parent_model.DoesNotExist:
                            # Parent doesn't exist, just store the ID
                            deleted_data['parent_data'][parent_model.__name__] = {
                                'field_name': field_name,
                                'id': parent_id
                            }
                
                # Handle special case: when deleting a FrenchExample, also delete its parent FrenchWord
                if model_class.__name__ == 'FrenchExample':
                    try:
                        # Get the parent FrenchWord
                        french_word_id = getattr(instance, 'french_word_id')
                        if french_word_id:
                            # First check if it's used by other examples
                            other_examples = model_class.objects.filter(french_word_id=french_word_id).exclude(id=instance_id).exists()
                            
                            # If this is the only example for this word, also delete the word
                            if not other_examples:
                                from django.apps import apps
                                FrenchWord = apps.get_model('words', 'FrenchWord')
                                french_word = FrenchWord.objects.get(id=french_word_id)
                                
                                # Store the FrenchWord data for potential restoration
                                deleted_data['parent_to_delete'] = {
                                    'model': 'FrenchWord',
                                    'data': cls._serialize_model_instance(french_word)
                                }
                                
                                # We'll delete the FrenchWord after deleting the example
                    except Exception as e:
                        logger.error(f"Error preparing to delete parent FrenchWord: {str(e)}")
                
                # Generate a unique key for this deletion operation
                operation_id = str(uuid.uuid4())
                
                try:
                    # Serialize to JSON string using custom encoder
                    json_data = json.dumps(deleted_data, cls=DjangoJSONEncoder)
                    # Store in cache for potential undo (expire after 1 hour)
                    cache.set(f"deletion_{operation_id}", json_data, 3600)
                except TypeError as e:
                    # Log the error with detailed traceback
                    logger.error(f"JSON serialization error: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Log the problem data for debugging
                    logger.error(f"Problem data: {deleted_data}")
                    return False, f"Error preparing data for caching: {str(e)}"
                
                # Perform the deletion
                instance.delete()
                
                # If this was a FrenchExample and we need to delete its parent FrenchWord
                if model_class.__name__ == 'FrenchExample' and 'parent_to_delete' in deleted_data:
                    try:
                        from django.apps import apps
                        FrenchWord = apps.get_model('words', 'FrenchWord')
                        french_word_id = getattr(instance, 'french_word_id')
                        if french_word_id:
                            # Double check that no other examples exist (might have been added in the meantime)
                            other_examples = model_class.objects.filter(french_word_id=french_word_id).exists()
                            if not other_examples:
                                FrenchWord.objects.filter(id=french_word_id).delete()
                                logger.info(f"Deleted parent FrenchWord with ID {french_word_id} because it had no other examples")
                    except Exception as e:
                        logger.error(f"Error deleting parent FrenchWord: {str(e)}")
                
                return True, operation_id
        except model_class.DoesNotExist:
            return False, f"{model_class.__name__} with ID {id_value} does not exist."
        except Exception as e:
            logger.error(f"Error deleting {model_class.__name__} with ID {id_value}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, str(e)
    
    @classmethod
    def delete_by_field_value(cls, model_class, field_name, field_value, delete_related_parent=False):
        """
        Delete records by a specific field value (such as foreign key).
        For example, delete all FrenchExamples with a specific french_word_id.
        
        Args:
            model_class: The Django model class
            field_name: The field to filter on (e.g., 'french_word_id')
            field_value: The value to filter for
            delete_related_parent: If True and the field is a foreign key, also delete the parent record
            
        Returns:
            Tuple of (success, message, count)
        """
        try:
            with transaction.atomic():
                # Validate field exists
                if not hasattr(model_class, field_name) and not field_name.endswith('_id'):
                    field_name = f"{field_name}_id"
                    if not hasattr(model_class, field_name):
                        return False, f"Field {field_name} does not exist on {model_class.__name__}", 0
                
                # Get instances that match the field value
                filter_kwargs = {field_name: field_value}
                instances = model_class.objects.filter(**filter_kwargs)
                count = instances.count()
                
                if count == 0:
                    return False, f"No {model_class.__name__} records found with {field_name}={field_value}", 0
                
                # Store deleted data for restoration
                deleted_data = {
                    'model': model_class.__name__,
                    'by_field': {
                        'field_name': field_name,
                        'field_value': field_value
                    },
                    'instances': [],
                    'related_data': {},
                    'parent_data': {}
                }
                
                # Get the parent model if this is a foreign key field
                parent_model = None
                parent_field = None
                parent_instance = None
                
                if field_name.endswith('_id'):
                    base_field_name = field_name[:-3]  # Remove _id suffix
                    for field in model_class._meta.fields:
                        if field.name == base_field_name and isinstance(field, models.ForeignKey):
                            parent_model = field.related_model
                            parent_field = field
                            break
                
                # Get the parent instance if needed
                if parent_model and delete_related_parent:
                    try:
                        parent_instance = parent_model.objects.get(id=field_value)
                        deleted_data['parent_to_delete'] = {
                            'model': parent_model.__name__,
                            'data': cls._serialize_model_instance(parent_instance)
                        }
                    except parent_model.DoesNotExist:
                        logger.warning(f"Parent {parent_model.__name__} with ID {field_value} does not exist")
                
                # Process each instance to be deleted
                instance_ids = []
                for instance in instances:
                    instance_ids.append(instance.id)
                    deleted_data['instances'].append(cls._serialize_model_instance(instance))
                
                # Get related data for each instance
                related_models = cls._get_related_models(model_class)
                for related_model in related_models:
                    # Initialize storage for this related model
                    if related_model.__name__ not in deleted_data['related_data']:
                        deleted_data['related_data'][related_model.__name__] = {
                            'instances': []
                        }
                    
                    # Find related instances for each field that could reference our model
                    for field in related_model._meta.fields:
                        if isinstance(field, models.ForeignKey) and field.related_model == model_class:
                            related_field_name = field.name
                            filter_kwargs = {f"{related_field_name}_id__in": instance_ids}
                            related_instances = related_model.objects.filter(**filter_kwargs)
                            
                            # Store field name once
                            if 'field_name' not in deleted_data['related_data'][related_model.__name__]:
                                deleted_data['related_data'][related_model.__name__]['field_name'] = related_field_name
                            
                            # Store each related instance
                            for rel_instance in related_instances:
                                rel_data = cls._serialize_model_instance(rel_instance)
                                parent_id = getattr(rel_instance, f"{related_field_name}_id")
                                rel_data['_parent_id'] = parent_id
                                deleted_data['related_data'][related_model.__name__]['instances'].append(rel_data)
                
                # Generate a unique key for this deletion operation
                operation_id = str(uuid.uuid4())
                
                try:
                    # Serialize to JSON string using custom encoder
                    json_data = json.dumps(deleted_data, cls=DjangoJSONEncoder)
                    # Store in cache for potential undo (expire after 1 hour)
                    cache.set(f"deletion_{operation_id}", json_data, 3600)
                except TypeError as e:
                    # Log the error with detailed traceback
                    logger.error(f"JSON serialization error: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return False, f"Error preparing data for caching: {str(e)}", 0
                
                # Perform the deletion of child records
                instances.delete()
                
                # Delete the parent if requested
                if parent_instance and delete_related_parent:
                    parent_instance.delete()
                    logger.info(f"Deleted parent {parent_model.__name__} with ID {field_value}")
                
                return True, operation_id, count
        except Exception as e:
            logger.error(f"Error deleting {model_class.__name__} records by {field_name}={field_value}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, str(e), 0
    
    @classmethod
    def delete_by_id_range(cls, model_class, start_id, end_id):
        """
        Delete records within an ID range and cache them for potential restoration.
        Returns a tuple of (success, message, count)
        """
        try:
            with transaction.atomic():
                # Get all instances in the ID range
                instances = model_class.objects.filter(id__gte=start_id, id__lte=end_id)
                count = instances.count()
                
                if count == 0:
                    return False, f"No {model_class.__name__} records found in the ID range {start_id} to {end_id}.", 0
                
                # Store deleted data for each instance
                deleted_data = {
                    'model': model_class.__name__,
                    'is_range': True,
                    'instances': [],
                    'related_data': {},
                    'manually_deleted_examples': []  # Track manually deleted examples
                }
                
                # Special handling to track manually deleted examples for FrenchWord
                if model_class.__name__ == 'FrenchWord':
                    from django.apps import apps
                    FrenchExample = apps.get_model('words', 'FrenchExample')
                    related_examples = FrenchExample.objects.filter(french_word_id__gte=start_id, french_word_id__lte=end_id)
                    
                    # If there are examples, store them for restoration
                    if related_examples.exists():
                        for example in related_examples:
                            example_data = cls._serialize_model_instance(example)
                            french_word_id = example.french_word_id
                            deleted_data['manually_deleted_examples'].append({
                                'model': 'FrenchExample',
                                'data': example_data,
                                'french_word_id': french_word_id
                            })
                        logger.info(f"Tracked {related_examples.count()} manually deleted examples for FrenchWord range {start_id}-{end_id}")
                
                # Get all related models
                related_models = cls._get_related_models(model_class)
                
                # Initialize related data structure
                for related_model in related_models:
                    deleted_data['related_data'][related_model.__name__] = {'instances': []}
                
                # Create a list of instance IDs for related data lookup
                instance_ids = list(instances.values_list('id', flat=True))
                
                # Process each instance
                for instance in instances:
                    # Store instance data
                    instance_data = cls._serialize_model_instance(instance)
                    deleted_data['instances'].append(instance_data)
                
                # For each related model, find and store instances related to our instances
                for related_model in related_models:
                    # Get the field name in the related model that points to our model
                    for field in related_model._meta.fields:
                        if isinstance(field, models.ForeignKey) and field.related_model == model_class:
                            related_field_name = field.name
                            # Use IDs for filtering instead of instance objects
                            filter_kwargs = {f"{related_field_name}_id__in": instance_ids}
                            related_instances = related_model.objects.filter(**filter_kwargs)
                            
                            # Process and store related instances
                            field_name_set = False
                            for rel_instance in related_instances:
                                rel_data = cls._serialize_model_instance(rel_instance)
                                # Get the parent ID from the foreign key field
                                parent_id = getattr(rel_instance, f"{related_field_name}_id")
                                rel_data['_parent_id'] = parent_id
                                deleted_data['related_data'][related_model.__name__]['instances'].append(rel_data)
                                if not field_name_set:
                                    deleted_data['related_data'][related_model.__name__]['field_name'] = related_field_name
                                    field_name_set = True
                
                # Generate a unique key for this deletion operation
                operation_id = str(uuid.uuid4())
                
                try:
                    # Serialize to JSON string using custom encoder
                    json_data = json.dumps(deleted_data, cls=DjangoJSONEncoder)
                    # Store in cache for potential undo (expire after 1 hour)
                    cache.set(f"deletion_{operation_id}", json_data, 3600)
                except TypeError as e:
                    # Log the error with detailed traceback
                    logger.error(f"JSON serialization error: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return False, f"Error preparing data for caching: {str(e)}", 0
                
                # Perform the deletion (this will cascade to related models)
                instances.delete()
                
                return True, operation_id, count
        except Exception as e:
            logger.error(f"Error deleting {model_class.__name__} records in range {start_id} to {end_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, str(e), 0
    
    @classmethod
    def delete_all(cls, model_class):
        """
        Delete all records from a model and cache them for potential restoration.
        Returns a tuple of (success, message, count)
        """
        try:
            with transaction.atomic():
                # Get all instances
                instances = model_class.objects.all()
                count = instances.count()
                
                if count == 0:
                    return False, f"No {model_class.__name__} records found to delete.", 0
                
                # Store deleted data for all instances
                deleted_data = {
                    'model': model_class.__name__,
                    'is_all': True,
                    'instances': [],
                    'related_data': {},
                    'manually_deleted_examples': []  # Track manually deleted examples
                }
                
                # Special handling to track manually deleted examples for FrenchWord
                if model_class.__name__ == 'FrenchWord':
                    from django.apps import apps
                    FrenchExample = apps.get_model('words', 'FrenchExample')
                    related_examples = FrenchExample.objects.all()
                    
                    # If there are examples, store them for restoration
                    if related_examples.exists():
                        for example in related_examples:
                            example_data = cls._serialize_model_instance(example)
                            french_word_id = example.french_word_id
                            deleted_data['manually_deleted_examples'].append({
                                'model': 'FrenchExample',
                                'data': example_data,
                                'french_word_id': french_word_id
                            })
                        logger.info(f"Tracked {related_examples.count()} manually deleted examples for all FrenchWords")
                
                # Get all related models
                related_models = cls._get_related_models(model_class)
                
                # Initialize related data structure
                for related_model in related_models:
                    deleted_data['related_data'][related_model.__name__] = {'instances': []}
                
                # Create a list of instance IDs for related data lookup
                instance_ids = list(instances.values_list('id', flat=True))
                
                # Process each instance
                for instance in instances:
                    # Store instance data
                    instance_data = cls._serialize_model_instance(instance)
                    deleted_data['instances'].append(instance_data)
                
                # For each related model, find and store instances related to our instances
                for related_model in related_models:
                    # Get the field name in the related model that points to our model
                    for field in related_model._meta.fields:
                        if isinstance(field, models.ForeignKey) and field.related_model == model_class:
                            related_field_name = field.name
                            # Use IDs for filtering instead of instance objects
                            filter_kwargs = {f"{related_field_name}_id__in": instance_ids}
                            related_instances = related_model.objects.filter(**filter_kwargs)
                            
                            # Process and store related instances
                            field_name_set = False
                            for rel_instance in related_instances:
                                rel_data = cls._serialize_model_instance(rel_instance)
                                # Get the parent ID from the foreign key field
                                parent_id = getattr(rel_instance, f"{related_field_name}_id")
                                rel_data['_parent_id'] = parent_id
                                deleted_data['related_data'][related_model.__name__]['instances'].append(rel_data)
                                if not field_name_set:
                                    deleted_data['related_data'][related_model.__name__]['field_name'] = related_field_name
                                    field_name_set = True
                
                # Generate a unique key for this deletion operation
                operation_id = str(uuid.uuid4())
                
                try:
                    # Serialize to JSON string using custom encoder
                    json_data = json.dumps(deleted_data, cls=DjangoJSONEncoder)
                    # Store in cache for potential undo (expire after 1 hour)
                    cache.set(f"deletion_{operation_id}", json_data, 3600)
                except TypeError as e:
                    # Log the error with detailed traceback
                    logger.error(f"JSON serialization error: {str(e)}")
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    return False, f"Error preparing data for caching: {str(e)}", 0
                
                # Perform the deletion (this will cascade to related models)
                instances.delete()
                
                return True, operation_id, count
        except Exception as e:
            logger.error(f"Error deleting all {model_class.__name__} records: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, str(e), 0
    
    @classmethod
    def undo_deletion(cls, operation_id):
        """
        Restore data that was deleted in a previous operation.
        Returns a tuple of (success, message, count)
        """
        try:
            # Get the cached deletion data
            deletion_key = f"deletion_{operation_id}"
            deletion_data_json = cache.get(deletion_key)
            
            if not deletion_data_json:
                return False, "No data found for the specified operation or the undo period has expired.", 0
            
            deletion_data = json.loads(deletion_data_json)
            
            with transaction.atomic():
                # Import the model dynamically
                from django.apps import apps
                model_name = deletion_data['model']
                model_class = apps.get_model('words', model_name)
                
                # Count how many records we'll restore
                count = 0
                examples_restored = 0
                
                # Restore parent instance first if it was deleted
                if 'parent_to_delete' in deletion_data:
                    parent_data = deletion_data['parent_to_delete']
                    parent_model_name = parent_data['model']
                    parent_model = apps.get_model('words', parent_model_name)
                    parent_instance_data = parent_data['data'].copy()
                    parent_id = parent_instance_data.pop('id', None)
                    
                    # Check if the parent already exists (might have been recreated)
                    parent_exists = parent_model.objects.filter(id=parent_id).exists()
                    if not parent_exists:
                        parent_instance = parent_model(**parent_instance_data)
                        if parent_id:
                            parent_instance.id = parent_id
                        parent_instance.save()
                        logger.info(f"Restored parent {parent_model_name} with ID {parent_id}")
                        count += 1
                
                # Handle deletion by field value
                if 'by_field' in deletion_data:
                    instances = deletion_data.get('instances', [])
                    count += len(instances)
                    
                    # Restore each instance
                    for instance_data in instances:
                        instance_id = instance_data.pop('id', None)
                        new_instance = model_class(**instance_data)
                        if instance_id:
                            new_instance.id = instance_id
                        new_instance.save()
                    
                    # Restore related instances
                    for related_model_name, related_data in deletion_data.get('related_data', {}).items():
                        if not related_data.get('instances'):
                            continue
                            
                        related_model = apps.get_model('words', related_model_name)
                        field_name = related_data.get('field_name')
                        
                        for rel_instance_data in related_data.get('instances', []):
                            parent_id = rel_instance_data.pop('_parent_id', None)
                            rel_id = rel_instance_data.pop('id', None)
                            
                            if parent_id:
                                try:
                                    parent_instance = model_class.objects.get(id=parent_id)
                                    rel_instance = related_model(**rel_instance_data)
                                    if rel_id:
                                        rel_instance.id = rel_id
                                    setattr(rel_instance, field_name, parent_instance)
                                    rel_instance.save()
                                except model_class.DoesNotExist:
                                    logger.warning(f"Parent {model_name} with ID {parent_id} not found during restoration")
                
                # Handling different deletion types
                elif 'is_all' in deletion_data or 'is_range' in deletion_data:
                    # For range or all deletions
                    instances = deletion_data.get('instances', [])
                    count += len(instances)
                    
                    # Restore main instances
                    for instance_data in instances:
                        instance_id = instance_data.pop('id', None)
                        new_instance = model_class(**instance_data)
                        if instance_id:
                            new_instance.id = instance_id  # Preserve original ID if available
                        new_instance.save()
                    
                    # Restore related instances
                    for related_model_name, related_data in deletion_data.get('related_data', {}).items():
                        related_model = apps.get_model('words', related_model_name)
                        field_name = related_data.get('field_name')
                        
                        for rel_instance_data in related_data.get('instances', []):
                            parent_id = rel_instance_data.pop('_parent_id', None)
                            if parent_id:
                                # Find the parent instance
                                try:
                                    parent_instance = model_class.objects.get(id=parent_id)
                                    # Create and save the related instance
                                    rel_instance = related_model(**rel_instance_data)
                                    setattr(rel_instance, field_name, parent_instance)
                                    rel_instance.save()
                                except model_class.DoesNotExist:
                                    logger.warning(f"Parent {model_name} with ID {parent_id} not found during restoration")
                else:
                    # For single record deletion
                    count += 1
                    # Restore the main instance
                    instance_data = deletion_data.get('data', {}).copy()
                    instance_id = instance_data.pop('id', None)
                    new_instance = model_class(**instance_data)
                    if instance_id:
                        new_instance.id = instance_id  # Preserve original ID if available
                    new_instance.save()
                    
                    # Restore related instances
                    for related_model_name, related_data in deletion_data.get('related_data', {}).items():
                        related_model = apps.get_model('words', related_model_name)
                        field_name = related_data.get('field_name')
                        
                        for rel_instance_data in related_data.get('instances', []):
                            # Get the ID and remove it from the data
                            rel_id = rel_instance_data.pop('id', None)
                            # Create and save the related instance
                            rel_instance = related_model(**rel_instance_data)
                            setattr(rel_instance, field_name, new_instance)
                            rel_instance.save()
                
                # Restore manually deleted examples
                if 'manually_deleted_examples' in deletion_data and deletion_data['manually_deleted_examples']:
                    examples = deletion_data['manually_deleted_examples']
                    FrenchExample = apps.get_model('words', 'FrenchExample')
                    
                    # First, clear any existing examples for this word to prevent duplicates
                    if model_name == 'FrenchWord' and 'is_all' not in deletion_data and 'is_range' not in deletion_data:
                        # For single word restoration, clear existing examples first
                        french_word_id = instance_id
                        FrenchExample.objects.filter(french_word_id=french_word_id).delete()
                        logger.info(f"Cleared existing examples for FrenchWord {french_word_id} to prevent duplicates")
                    
                    for example_data in examples:
                        try:
                            # Get the data and French word ID
                            example_instance_data = example_data['data'].copy()
                            example_id = example_instance_data.pop('id', None)
                            french_word_id = example_data['french_word_id']
                            
                            # Try to find the parent FrenchWord
                            try:
                                FrenchWord = apps.get_model('words', 'FrenchWord')
                                
                                # Make sure the parent word exists (it should be restored by now)
                                french_word = None
                                try:
                                    french_word = FrenchWord.objects.get(id=french_word_id)
                                except FrenchWord.DoesNotExist:
                                    logger.warning(f"Parent FrenchWord {french_word_id} not found, recreating it")
                                    # If for some reason the parent wasn't restored, recreate it
                                    french_word = FrenchWord(id=french_word_id)
                                    french_word.save()
                                
                                # Create the example with reference to the parent
                                example = FrenchExample(**example_instance_data)
                                if example_id:
                                    example.id = example_id
                                example.french_word = french_word
                                example.save()
                                examples_restored += 1
                            except Exception as e:
                                logger.error(f"Error restoring example: {str(e)}")
                                logger.error(f"Traceback: {traceback.format_exc()}")
                        except Exception as e:
                            logger.error(f"Error processing example data: {str(e)}")
                            logger.error(f"Traceback: {traceback.format_exc()}")
                    
                    if examples_restored > 0:
                        logger.info(f"Restored {examples_restored} manually deleted examples")
                
                # Remove the cached data
                cache.delete(deletion_key)
                
                total_restored = count + examples_restored
                return True, f"Successfully restored {total_restored} records and their related data.", total_restored
        except Exception as e:
            logger.error(f"Error restoring data for operation {operation_id}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return False, str(e), 0

# Function to get all model choices for the UI
def get_model_choices():
    """
    Returns a list of tuples with (model_name, display_name) for all app models
    """
    from django.apps import apps
    
    models = []
    for model in apps.get_models():
        if model._meta.app_label == 'words':  # Only include models from our app
            models.append((model.__name__, model._meta.verbose_name))
    
    return sorted(models, key=lambda x: x[1])

# Function to get field choices for a model
def get_field_choices(model_name):
    """
    Returns a list of tuples with (field_name, display_name) for a model
    """
    from django.apps import apps
    
    try:
        model = apps.get_model('words', model_name)
        fields = []
        
        # Add the primary key
        fields.append(('id', 'ID (Primary Key)'))
        
        # Add foreign key fields
        for field in model._meta.fields:
            if isinstance(field, models.ForeignKey):
                fields.append((f"{field.name}_id", f"{field.verbose_name} ID (Foreign Key to {field.related_model.__name__})"))
        
        return fields
    except LookupError:
        return [('id', 'ID')] 