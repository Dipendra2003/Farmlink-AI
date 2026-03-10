"""
Enhanced Expert Forum Routes - Complete Consolidated Version
Includes all forum features: posts, replies, voting, following, drafts, moderation, notifications, etc.
"""

# Standard library imports
from datetime import datetime, timedelta

# Third-party imports
from flask import render_template, redirect, url_for, flash, request, jsonify, abort, session
from flask_login import login_required, current_user
from sqlalchemy import desc, asc, func, and_, or_

# Local imports
from app import app, db
from models import (
    User, ExpertPost, ExpertReply, PostVote, ReplyVote, UserFollow,
    PostDraft, ContentReport, EditHistory, ForumNotification, PostLock, UserRating
)
from forms import (
    ExpertPostForm, ExpertReplyForm, ReportContentForm, PostDraftForm,
    AdvancedSearchForm, NotificationPreferencesForm, ModerationForm
)
from role_hierarchy import admin_required
from expert_forum_utils import (
    calculate_user_reputation, get_avg_rating, calculate_vote_weight,
    create_notification, check_spam_content, update_post_votes,
    update_reply_votes, log_edit_history
)

# ============================================================================
# MAIN FORUM ROUTES
# ============================================================================

@app.route('/expert-forum')
def expert_forum():
    """Enhanced expert forum with filtering and advanced search"""
    from category_config import CATEGORY_STRUCTURE, get_category_display_name
    
    page = request.args.get('page', 1, type=int)
    main_category = request.args.get('main_category', 'all')
    subcategory = request.args.get('subcategory', 'all')
    sort_by = request.args.get('sort', 'recent')
    search_query = request.args.get('q', '')
    post_type = request.args.get('post_type', 'all')
    date_range = request.args.get('date_range', 'all')
    
    # Base query
    query = ExpertPost.query
    
    # Apply category filter
    if main_category != 'all':
        query = query.filter_by(main_category=main_category)
        if subcategory != 'all':
            query = query.filter_by(subcategory=subcategory)
    
    # Apply post type filter    
    if post_type == 'questions':
        query = query.filter_by(is_question=True)
    elif post_type == 'discussions':
        query = query.filter_by(is_question=False)
    elif post_type == 'answered':
        query = query.filter_by(is_answered=True)
    elif post_type == 'unanswered':
        query = query.filter_by(is_answered=False)
    
    # Apply date range filter
    if date_range != 'all':
        now = datetime.utcnow()
        if date_range == 'today':
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == 'week':
            start_date = now - timedelta(days=7)
        elif date_range == 'month':
            start_date = now - timedelta(days=30)
        elif date_range == 'year':
            start_date = now - timedelta(days=365)
        else:
            start_date = None
            
        if start_date:
            query = query.filter(ExpertPost.created_at >= start_date)
        
    # Apply search query
    if search_query:
        query = query.filter(
            or_(
                ExpertPost.title.contains(search_query),
                ExpertPost.content.contains(search_query),
                ExpertPost.tags.contains(search_query)
            )
        )
    
    # Apply sorting
    if sort_by == 'popular':
        query = query.order_by(desc(ExpertPost.upvotes - ExpertPost.downvotes))
    elif sort_by == 'views':
        query = query.order_by(desc(ExpertPost.views))
    elif sort_by == 'replies':
        query = query.outerjoin(ExpertReply).group_by(ExpertPost.id).order_by(desc(func.count(ExpertReply.id)))
    else:  # recent
        query = query.order_by(desc(ExpertPost.created_at))
    
    # Paginate
    posts = query.paginate(
        page=page, per_page=15, error_out=False
    )
    
    return render_template('expert_forum/index.html',
                         posts=posts,
                         category_structure=CATEGORY_STRUCTURE,
                         current_main_category=main_category,
                         current_subcategory=subcategory,
                         current_sort=sort_by,
                         search_query=search_query,
                         get_category_display_name=get_category_display_name)

@app.route('/expert-forum/create', methods=['GET', 'POST'])
@login_required
def create_expert_post():
    """Create new expert forum post with spam detection"""
    from category_config import CATEGORY_STRUCTURE, get_subcategories
    form = ExpertPostForm()
    
    # Populate subcategory choices based on selected main category
    if request.method == 'POST' and form.main_category.data:
        form.subcategory.choices = [('', 'Select Subcategory')] + get_subcategories(form.main_category.data)
    
    if form.validate_on_submit():
        # Check for spam
        if check_spam_content(form.content.data, current_user.id):
            flash('Your post appears to be spam. Please try again later.', 'warning')
            return render_template('expert_forum/create_post.html', form=form, category_structure=CATEGORY_STRUCTURE)
        
        try:
            post = ExpertPost(
                title=form.title.data,
                content=form.content.data,
                category=form.subcategory.data,  # Keep for backward compatibility
                main_category=form.main_category.data,
                subcategory=form.subcategory.data,
                tags=form.tags.data,
                is_question=form.is_question.data,
                author_id=current_user.id
            )
            
            db.session.add(post)
            db.session.commit()
            
            # Notify followers (in separate try-catch to not fail post creation)
            try:
                from models import User
                # Join with User table to ensure follower still exists
                followers = db.session.query(UserFollow).join(
                    User, UserFollow.follower_id == User.id
                ).filter(UserFollow.followed_id == current_user.id).all()
                
                for follow in followers:
                    create_notification(
                        user_id=follow.follower_id,
                        notification_type='new_post',
                        title=f'New post from {current_user.full_name or current_user.username}',
                        message=f'"{post.title}"',
                        sender_id=current_user.id,
                        post_id=post.id
                    )
            except Exception as notif_error:
                app.logger.error(f'Error sending notifications: {str(notif_error)}')
                # Continue anyway - post was created successfully
            
            flash('Post created successfully!', 'success')
            return redirect(url_for('view_expert_post', post_id=post.id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error creating post: {str(e)}')
            flash('An error occurred while creating your post.', 'danger')
    
    return render_template('expert_forum/create_post.html', form=form, category_structure=CATEGORY_STRUCTURE)

@app.route('/expert-forum/api/subcategories/<main_category>')
def get_subcategories(main_category):
    """API endpoint to get subcategories for a main category"""
    from category_config import get_subcategories
    subcategories = get_subcategories(main_category)
    return jsonify({'subcategories': subcategories})

@app.route('/expert-forum/post/<int:post_id>')
def view_expert_post(post_id):
    """View individual expert post with enhanced features"""
    post = ExpertPost.query.get_or_404(post_id)
    
    # Check if post is locked
    if post.is_locked_active and current_user.role != 'admin':
        flash('This post is currently locked.', 'warning')
    
    # Increment views (only once per session)
    if f'viewed_post_{post_id}' not in session:
        post.views += 1
        db.session.commit()
        session[f'viewed_post_{post_id}'] = True
    
    # Get replies with vote information
    replies = ExpertReply.query.filter_by(post_id=post_id).order_by(
        desc(ExpertReply.is_solution),
        desc(ExpertReply.upvotes - ExpertReply.downvotes),
        asc(ExpertReply.created_at)
    ).all()
    
    # Get user's votes if logged in
    user_post_vote = None
    user_reply_votes = {}
    is_following_author = False
    if current_user.is_authenticated:
        user_post_vote = post.get_user_vote(current_user.id)
        for reply in replies:
            user_reply_votes[reply.id] = reply.get_user_vote(current_user.id)
        # Check if current user is following the post author
        is_following_author = current_user.is_following(post.author)
    
    # Get reply form
    reply_form = ExpertReplyForm()
    
    from category_config import get_category_display_name
    return render_template('expert_forum/post_detail.html',
                         post=post,
                         replies=replies,
                         reply_form=reply_form,
                         user_post_vote=user_post_vote,
                         user_reply_votes=user_reply_votes,
                         is_following_author=is_following_author,
                         get_category_display_name=get_category_display_name)

@app.route('/expert-forum/post/<int:post_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_expert_post(post_id):
    """Edit expert forum post with history tracking"""
    from category_config import CATEGORY_STRUCTURE, get_subcategories
    post = ExpertPost.query.get_or_404(post_id)
    
    # Check permissions
    if current_user.id != post.author_id and current_user.role != 'admin':
        flash('You can only edit your own posts.', 'danger')
        return redirect(url_for('view_expert_post', post_id=post_id))
    
    # Check if post is locked
    if post.is_locked_active and current_user.role != 'admin':
        flash('This post is locked and cannot be edited.', 'warning')
        return redirect(url_for('view_expert_post', post_id=post_id))
    
    form = ExpertPostForm()
    
    # Populate subcategory choices based on selected main category
    if request.method == 'POST' and form.main_category.data:
        form.subcategory.choices = [('', 'Select Subcategory')] + get_subcategories(form.main_category.data)
    elif request.method == 'GET' and post.main_category:
        form.subcategory.choices = [('', 'Select Subcategory')] + get_subcategories(post.main_category)
    
    if form.validate_on_submit():
        try:
            # Log changes
            if post.title != form.title.data:
                log_edit_history('post', post.id, 'title', post.title, form.title.data, current_user.id)
            if post.content != form.content.data:
                log_edit_history('post', post.id, 'content', post.content, form.content.data, current_user.id)
            
            # Update post
            post.title = form.title.data
            post.content = form.content.data
            post.category = form.subcategory.data  # Keep for backward compatibility
            post.main_category = form.main_category.data
            post.subcategory = form.subcategory.data
            post.tags = form.tags.data
            post.is_question = form.is_question.data
            post.updated_at = datetime.utcnow()
            
            db.session.commit()
            flash('Post updated successfully!', 'success')
            return redirect(url_for('view_expert_post', post_id=post.id))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error updating post: {str(e)}')
            flash('An error occurred while updating your post.', 'danger')
    elif request.method == 'GET':
        # Populate form with existing data
        form.title.data = post.title
        form.content.data = post.content
        form.main_category.data = post.main_category
        form.subcategory.data = post.subcategory
        form.tags.data = post.tags
        form.is_question.data = post.is_question
    
    return render_template('expert_forum/edit_post.html', form=form, post=post, category_structure=CATEGORY_STRUCTURE)

@app.route('/expert-forum/post/<int:post_id>/delete', methods=['POST'])
@login_required
def delete_expert_post(post_id):
    """Delete expert forum post (hard delete)"""
    post = ExpertPost.query.get_or_404(post_id)
    
    # Check permissions - only post author or admin can delete
    if current_user.id != post.author_id and current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'You can only delete your own posts'}), 403
    
    try:
        # Get all reply IDs before deletion
        reply_ids = [reply.id for reply in ExpertReply.query.filter_by(post_id=post_id).all()]
        
        # Delete all reply votes for replies under this post
        if reply_ids:
            ReplyVote.query.filter(ReplyVote.reply_id.in_(reply_ids)).delete(synchronize_session=False)
            db.session.flush()
            
            # Delete notifications for replies
            ForumNotification.query.filter(ForumNotification.reply_id.in_(reply_ids)).delete(synchronize_session=False)
            db.session.flush()
            
            # Delete reports for replies
            ContentReport.query.filter(
                db.or_(
                    db.and_(ContentReport.content_type == 'reply', ContentReport.content_id.in_(reply_ids)),
                    ContentReport.reply_id.in_(reply_ids)
                )
            ).delete(synchronize_session=False)
            db.session.flush()
            
            # Delete edit history for replies
            EditHistory.query.filter(
                db.and_(EditHistory.content_type == 'reply', EditHistory.content_id.in_(reply_ids))
            ).delete(synchronize_session=False)
            db.session.flush()
        
        # Delete all related replies
        ExpertReply.query.filter_by(post_id=post_id).delete(synchronize_session=False)
        db.session.flush()
        
        # Delete all votes for this post
        PostVote.query.filter_by(post_id=post_id).delete(synchronize_session=False)
        db.session.flush()
        
        # Delete notifications for this post
        ForumNotification.query.filter_by(post_id=post_id).delete(synchronize_session=False)
        db.session.flush()
        
        # Delete reports for this post
        ContentReport.query.filter(
            db.or_(
                db.and_(ContentReport.content_type == 'post', ContentReport.content_id == post_id),
                ContentReport.post_id == post_id
            )
        ).delete(synchronize_session=False)
        db.session.flush()
        
        # Delete edit history for this post
        EditHistory.query.filter(
            db.and_(EditHistory.content_type == 'post', EditHistory.content_id == post_id)
        ).delete(synchronize_session=False)
        db.session.flush()
        
        # Delete the post
        db.session.delete(post)
        db.session.commit()
        
        flash('Post deleted successfully.', 'success')
        return jsonify({
            'success': True, 
            'redirect': url_for('expert_forum'),
            'message': 'Post deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error deleting post: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to delete post. Please try again.'}), 400

# ============================================================================
# REPLY ROUTES
# ============================================================================

@app.route('/expert-forum/post/<int:post_id>/reply', methods=['POST'])
@login_required
def reply_to_expert_post(post_id):
    """Reply to expert forum post"""
    post = ExpertPost.query.get_or_404(post_id)
    
    # Check if post is locked
    if post.is_locked_active and current_user.role != 'admin':
        flash('This post is locked. New replies are not allowed.', 'warning')
        return redirect(url_for('view_expert_post', post_id=post_id))
    
    form = ExpertReplyForm()
    
    if form.validate_on_submit():
        try:
            reply = ExpertReply(
                content=form.content.data,
                expertise=form.expertise.data,
                post_id=post_id,
                author_id=current_user.id
            )
            
            db.session.add(reply)
            db.session.commit()
            
            # Notify post author
            if post.author_id != current_user.id:
                create_notification(
                    user_id=post.author_id,
                    notification_type='new_reply',
                    title='New reply to your post',
                    message=f'{current_user.full_name or current_user.username} replied to "{post.title}"',
                    sender_id=current_user.id,
                    post_id=post_id,
                    reply_id=reply.id
                )
            
            flash('Reply added successfully!', 'success')
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error adding reply: {str(e)}')
            flash('An error occurred while posting your reply.', 'danger')
    
    return redirect(url_for('view_expert_post', post_id=post_id))

@app.route('/expert-forum/reply/<int:reply_id>/mark-solution', methods=['POST'])
@login_required
def mark_reply_as_solution(reply_id):
    """Mark a reply as the solution"""
    reply = ExpertReply.query.get_or_404(reply_id)
    post = reply.post
    
    # Only post author can mark solutions
    if current_user.id != post.author_id:
        return jsonify({'success': False, 'message': 'Only the post author can mark solutions'}), 403
    
    try:
        # Unmark other solutions for this post
        ExpertReply.query.filter_by(post_id=post.id, is_solution=True).update({'is_solution': False})
        
        # Mark this reply as solution
        reply.is_solution = True
        post.is_answered = True
        
        db.session.commit()
        
        # Notify reply author
        if reply.author_id != current_user.id:
            create_notification(
                user_id=reply.author_id,
                notification_type='solution_marked',
                title='Your reply was marked as solution!',
                message=f'Your reply to "{post.title}" was marked as the solution',
                sender_id=current_user.id,
                post_id=post.id,
                reply_id=reply.id
            )
        
        return jsonify({'success': True, 'message': 'Reply marked as solution'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error marking solution: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to mark solution'}), 400

@app.route('/expert-forum/reply/<int:reply_id>/delete', methods=['POST'])
@login_required
def delete_expert_reply(reply_id):
    """Delete expert forum reply"""
    reply = ExpertReply.query.get_or_404(reply_id)
    
    # Check permissions - only reply author or admin can delete
    if current_user.id != reply.author_id and current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'You can only delete your own replies'}), 403
    
    try:
        # Store post_id for redirect
        post_id = reply.post_id
        
        # Delete all votes for this reply first
        try:
            ReplyVote.query.filter_by(reply_id=reply_id).delete(synchronize_session=False)
            db.session.flush()
        except Exception as vote_error:
            app.logger.warning(f'Error deleting reply votes: {str(vote_error)}')
        
        # Delete any notifications related to this reply
        try:
            ForumNotification.query.filter_by(reply_id=reply_id).delete(synchronize_session=False)
            db.session.flush()
        except Exception as notif_error:
            app.logger.warning(f'Error deleting reply notifications: {str(notif_error)}')
        
        # Delete any reports related to this reply
        try:
            # Delete using both old and new foreign key patterns
            ContentReport.query.filter(
                db.or_(
                    db.and_(ContentReport.content_type == 'reply', ContentReport.content_id == reply_id),
                    ContentReport.reply_id == reply_id
                )
            ).delete(synchronize_session=False)
            db.session.flush()
        except Exception as report_error:
            app.logger.warning(f'Error deleting reply reports: {str(report_error)}')
        
        # Delete any edit history for this reply
        try:
            EditHistory.query.filter_by(content_type='reply', content_id=reply_id).delete(synchronize_session=False)
            db.session.flush()
        except Exception as history_error:
            app.logger.warning(f'Error deleting reply history: {str(history_error)}')
        
        # Finally delete the reply itself
        db.session.delete(reply)
        db.session.commit()
        
        app.logger.info(f'Reply {reply_id} deleted successfully by user {current_user.id}')
        
        return jsonify({
            'success': True, 
            'message': 'Reply deleted successfully',
            'post_id': post_id
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error deleting reply {reply_id}: {str(e)}')
        import traceback
        app.logger.error(f'Traceback: {traceback.format_exc()}')
        return jsonify({'success': False, 'message': f'Failed to delete reply: {str(e)}'}), 400

# ============================================================================
# VOTING ROUTES
# ============================================================================

@app.route('/expert-forum/post/<int:post_id>/vote', methods=['POST'])
@login_required
def vote_on_post(post_id):
    """Vote on a post (upvote/downvote with weight)"""
    from sqlalchemy.exc import IntegrityError
    
    post = ExpertPost.query.get_or_404(post_id)
    vote_type = request.json.get('vote_type')  # 'upvote' or 'downvote'
    
    if vote_type not in ['upvote', 'downvote']:
        return jsonify({'success': False, 'message': 'Invalid vote type'}), 400
    
    try:
        # Check existing vote using a fresh query
        existing_vote = PostVote.query.filter_by(
            post_id=post_id,
            user_id=current_user.id
        ).first()
        
        action = None
        
        if existing_vote:
            if existing_vote.vote_type == vote_type:
                # Remove vote if same type (toggle off)
                vote_id = existing_vote.id
                PostVote.query.filter_by(id=vote_id).delete()
                action = 'removed'
            else:
                # Change vote type
                existing_vote.vote_type = vote_type
                existing_vote.weight = calculate_vote_weight(current_user)
                existing_vote.updated_at = datetime.utcnow()
                action = 'changed'
        else:
            # New vote - create it
            new_vote = PostVote(
                post_id=post_id,
                user_id=current_user.id,
                vote_type=vote_type,
                weight=calculate_vote_weight(current_user)
            )
            db.session.add(new_vote)
            action = 'added'
        
        db.session.commit()
        
        # Recalculate vote counts from database
        upvote_count = PostVote.query.filter_by(post_id=post_id, vote_type='upvote').count()
        downvote_count = PostVote.query.filter_by(post_id=post_id, vote_type='downvote').count()
        
        # Update post vote counts
        post.upvotes = upvote_count
        post.downvotes = downvote_count
        db.session.commit()
        
        # Notify post author for upvotes
        if vote_type == 'upvote' and action == 'added' and post.author_id != current_user.id:
            try:
                create_notification(
                    user_id=post.author_id,
                    notification_type='post_upvoted',
                    title='Your post was upvoted!',
                    message=f'Your post "{post.title}" received an upvote',
                    sender_id=current_user.id,
                    post_id=post_id
                )
            except Exception as notif_error:
                app.logger.warning(f'Failed to send vote notification: {str(notif_error)}')
        
        app.logger.info(f'Vote action: {action} for post {post_id} by user {current_user.id}. Upvotes: {upvote_count}, Downvotes: {downvote_count}')
        
        return jsonify({
            'success': True,
            'action': action,
            'upvotes': upvote_count,
            'downvotes': downvote_count,
            'score': upvote_count - downvote_count
        })
        
    except IntegrityError as e:
        db.session.rollback()
        error_msg = str(e)
        app.logger.error(f'IntegrityError voting on post {post_id}: {error_msg}')
        
        # Duplicate key - vote already exists, try to toggle it
        if 'Duplicate' in error_msg or 'duplicate key' in error_msg.lower() or 'unique' in error_msg.lower():
            try:
                existing_vote = PostVote.query.filter_by(post_id=post_id, user_id=current_user.id).first()
                
                if existing_vote:
                    if existing_vote.vote_type == vote_type:
                        PostVote.query.filter_by(id=existing_vote.id).delete()
                        action = 'removed'
                    else:
                        existing_vote.vote_type = vote_type
                        existing_vote.weight = calculate_vote_weight(current_user)
                        action = 'changed'
                    
                    db.session.commit()
                    
                    upvote_count = PostVote.query.filter_by(post_id=post_id, vote_type='upvote').count()
                    downvote_count = PostVote.query.filter_by(post_id=post_id, vote_type='downvote').count()
                    
                    post.upvotes = upvote_count
                    post.downvotes = downvote_count
                    db.session.commit()
                    
                    return jsonify({
                        'success': True,
                        'action': action,
                        'upvotes': upvote_count,
                        'downvotes': downvote_count,
                        'score': upvote_count - downvote_count
                    })
            except Exception as retry_error:
                db.session.rollback()
                app.logger.error(f'Retry failed: {str(retry_error)}')
        
        return jsonify({'success': False, 'message': 'Failed to vote. Please try again.'}), 400
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error voting on post {post_id}: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to vote. Please try again.'}), 400

@app.route('/expert-forum/reply/<int:reply_id>/vote', methods=['POST'])
@login_required
def vote_on_reply(reply_id):
    """Vote on a reply (upvote/downvote with weight)"""
    from sqlalchemy.exc import IntegrityError
    
    reply = ExpertReply.query.get_or_404(reply_id)
    vote_type = request.json.get('vote_type')  # 'upvote' or 'downvote'
    
    if vote_type not in ['upvote', 'downvote']:
        return jsonify({'success': False, 'message': 'Invalid vote type'}), 400
    
    try:
        # Check existing vote using a fresh query
        existing_vote = ReplyVote.query.filter_by(
            reply_id=reply_id,
            user_id=current_user.id
        ).first()
        
        action = None
        
        if existing_vote:
            if existing_vote.vote_type == vote_type:
                # Remove vote if same type (toggle off)
                vote_id = existing_vote.id
                ReplyVote.query.filter_by(id=vote_id).delete()
                action = 'removed'
            else:
                # Change vote type
                existing_vote.vote_type = vote_type
                existing_vote.weight = calculate_vote_weight(current_user)
                existing_vote.updated_at = datetime.utcnow()
                action = 'changed'
        else:
            # New vote - create it
            new_vote = ReplyVote(
                reply_id=reply_id,
                user_id=current_user.id,
                vote_type=vote_type,
                weight=calculate_vote_weight(current_user)
            )
            db.session.add(new_vote)
            action = 'added'
        
        db.session.commit()
        
        # Recalculate vote counts from database
        upvote_count = ReplyVote.query.filter_by(reply_id=reply_id, vote_type='upvote').count()
        downvote_count = ReplyVote.query.filter_by(reply_id=reply_id, vote_type='downvote').count()
        
        # Update reply vote counts
        reply.upvotes = upvote_count
        reply.downvotes = downvote_count
        db.session.commit()
        
        # Notify reply author for upvotes
        if vote_type == 'upvote' and action == 'added' and reply.author_id != current_user.id:
            try:
                create_notification(
                    user_id=reply.author_id,
                    notification_type='reply_upvoted',
                    title='Your reply was upvoted!',
                    message=f'Your reply in "{reply.post.title}" received an upvote',
                    sender_id=current_user.id,
                    post_id=reply.post_id,
                    reply_id=reply_id
                )
            except Exception as notif_error:
                app.logger.warning(f'Failed to send vote notification: {str(notif_error)}')
        
        app.logger.info(f'Vote action: {action} for reply {reply_id} by user {current_user.id}. Upvotes: {upvote_count}, Downvotes: {downvote_count}')
        
        return jsonify({
            'success': True,
            'action': action,
            'upvotes': upvote_count,
            'downvotes': downvote_count,
            'score': upvote_count - downvote_count
        })
        
    except IntegrityError as e:
        db.session.rollback()
        error_msg = str(e)
        app.logger.error(f'IntegrityError voting on reply {reply_id}: {error_msg}')
        
        # Duplicate key - vote already exists, try to toggle it
        if 'Duplicate' in error_msg or 'duplicate key' in error_msg.lower() or 'unique' in error_msg.lower():
            try:
                existing_vote = ReplyVote.query.filter_by(reply_id=reply_id, user_id=current_user.id).first()
                
                if existing_vote:
                    if existing_vote.vote_type == vote_type:
                        ReplyVote.query.filter_by(id=existing_vote.id).delete()
                        action = 'removed'
                    else:
                        existing_vote.vote_type = vote_type
                        existing_vote.weight = calculate_vote_weight(current_user)
                        action = 'changed'
                    
                    db.session.commit()
                    
                    upvote_count = ReplyVote.query.filter_by(reply_id=reply_id, vote_type='upvote').count()
                    downvote_count = ReplyVote.query.filter_by(reply_id=reply_id, vote_type='downvote').count()
                    
                    reply.upvotes = upvote_count
                    reply.downvotes = downvote_count
                    db.session.commit()
                    
                    return jsonify({
                        'success': True,
                        'action': action,
                        'upvotes': upvote_count,
                        'downvotes': downvote_count,
                        'score': upvote_count - downvote_count
                    })
            except Exception as retry_error:
                db.session.rollback()
                app.logger.error(f'Retry failed: {str(retry_error)}')
        
        return jsonify({'success': False, 'message': 'Failed to vote. Please try again.'}), 400
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error voting on reply {reply_id}: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to vote. Please try again.'}), 400

# ============================================================================
# FOLLOWING ROUTES
# ============================================================================

@app.route('/expert-forum/user/<int:user_id>/follow', methods=['POST'])
@login_required
def follow_user(user_id):
    """Follow/unfollow a user"""
    from sqlalchemy.exc import IntegrityError, OperationalError
    
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'You cannot follow yourself'}), 400
    
    try:
        # Expire any cached data to get fresh state from database
        db.session.expire_all()
        
        # Direct database query to check follow status (avoid stale cache)
        existing_follow = UserFollow.query.filter_by(
            follower_id=current_user.id,
            followed_id=user.id
        ).first()
        
        if existing_follow:
            # Already following - unfollow
            db.session.delete(existing_follow)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'action': 'unfollowed',
                'message': f'You are no longer following {user.full_name or user.username}',
                'follower_count': user.get_follower_count()
            })
        else:
            # Not following - follow
            new_follow = UserFollow(
                follower_id=current_user.id,
                followed_id=user.id
            )
            db.session.add(new_follow)
            db.session.commit()
            
            # Send notification
            try:
                create_notification(
                    user_id=user.id,
                    notification_type='new_follower',
                    title='New follower!',
                    message=f'{current_user.full_name or current_user.username} started following you',
                    sender_id=current_user.id
                )
            except Exception as notif_error:
                app.logger.warning(f'Failed to send follow notification: {str(notif_error)}')
            
            return jsonify({
                'success': True,
                'action': 'followed',
                'message': f'You are now following {user.full_name or user.username}',
                'follower_count': user.get_follower_count()
            })
            
    except IntegrityError as e:
        db.session.rollback()
        error_msg = str(e)
        
        # Duplicate key means user is already following - handle as unfollow request
        if 'Duplicate' in error_msg or 'unique' in error_msg.lower():
            # Race condition: record was inserted between our check and insert
            # Treat this as an unfollow request
            db.session.expire_all()
            existing_follow = UserFollow.query.filter_by(
                follower_id=current_user.id,
                followed_id=user.id
            ).first()
            
            if existing_follow:
                db.session.delete(existing_follow)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'action': 'unfollowed',
                    'message': f'You are no longer following {user.full_name or user.username}',
                    'follower_count': user.get_follower_count()
                })
            else:
                return jsonify({
                    'success': True,
                    'action': 'followed',
                    'message': f'You are now following {user.full_name or user.username}',
                    'follower_count': user.get_follower_count()
                })
        
        app.logger.error(f'Database error in follow/unfollow: {error_msg}')
        return jsonify({'success': False, 'message': 'Failed to update follow status. Please try again.'}), 400
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error following/unfollowing user {user_id}: {str(e)}')
        return jsonify({
            'success': False, 
            'message': 'An error occurred while updating follow status. Please try again.'
        }), 500
    
    # Should not reach here, but just in case
    return jsonify({'success': False, 'message': 'Server is busy. Please try again later.'}), 503

@app.route('/expert-forum/user/<int:user_id>')
def expert_user_profile(user_id):
    """View user profile with forum statistics"""
    user = User.query.get_or_404(user_id)
    
    # Get user's forum statistics (now includes rating stats)
    stats = calculate_user_reputation(user_id)
    
    # Add follower counts
    stats.update({
        'follower_count': user.get_follower_count(),
        'following_count': user.get_following_count()
    })
    
    # Get recent posts and replies
    recent_posts = ExpertPost.query.filter_by(author_id=user_id).order_by(desc(ExpertPost.created_at)).limit(10).all()
    recent_replies = ExpertReply.query.filter_by(author_id=user_id).order_by(desc(ExpertReply.created_at)).limit(10).all()
    
    # Check if current user is following this user
    is_following = False
    if current_user.is_authenticated:
        is_following = current_user.is_following(user)
    
    return render_template('expert_forum/user_profile.html',
                         user=user,
                         stats=stats,
                         posts=recent_posts,
                         replies=recent_replies,
                         is_following=is_following,
                         get_avg_rating=get_avg_rating)

# ============================================================================
# USER RATING SYSTEM
# ============================================================================

@app.route('/expert-forum/user/<int:user_id>/rate', methods=['POST'])
@login_required
def forum_rate_user(user_id):
    """Rate a user (1-5 stars) in forum context"""
    app.logger.info(f'Rating user {user_id} by current_user {current_user.id}')
    
    if user_id == current_user.id:
        app.logger.warning(f'User {current_user.id} tried to rate themselves')
        return jsonify({'success': False, 'message': 'Cannot rate yourself'}), 400
    
    user = User.query.get_or_404(user_id)
    
    try:
        # Log the incoming request data for debugging
        app.logger.info(f'Rating request data: {request.json}')
        
        rating_value = request.json.get('rating') if request.json else None
        if rating_value is None:
            app.logger.error(f'No rating value in request. JSON: {request.json}, Data: {request.data}')
            return jsonify({'success': False, 'message': 'Rating is required'}), 400
        
        rating_value = int(rating_value)
        # Accept both 'comment' and 'feedback' for backwards compatibility
        feedback = request.json.get('comment') or request.json.get('feedback', '')
        if feedback:
            feedback = feedback.strip()
        
        app.logger.info(f'Parsed rating: {rating_value}, feedback: {feedback}')
        
        if not (1 <= rating_value <= 5):
            app.logger.error(f'Invalid rating value: {rating_value}')
            return jsonify({'success': False, 'message': 'Rating must be between 1 and 5'}), 400
        
        # Check if user already rated this user
        app.logger.info(f'Checking for existing rating from {current_user.id} to {user_id}')
        existing_rating = UserRating.query.filter_by(
            rater_id=current_user.id,
            rated_user_id=user_id
        ).first()
        app.logger.info(f'Existing rating found: {existing_rating is not None}')
        
        if existing_rating:
            # Update existing rating
            app.logger.info(f'Updating existing rating {existing_rating.id}')
            existing_rating.rating = rating_value
            existing_rating.feedback = feedback
            message = 'Rating updated successfully'
        else:
            # Create new rating
            app.logger.info(f'Creating new rating')
            new_rating = UserRating(
                rater_id=current_user.id,
                rated_user_id=user_id,
                rating=rating_value,
                feedback=feedback,
                transaction_type='forum'
            )
            db.session.add(new_rating)
            message = 'Rating submitted successfully'
        
        app.logger.info(f'Committing rating to database')
        db.session.commit()
        app.logger.info(f'Rating committed successfully')
        
        # Calculate new rating statistics
        from expert_forum_utils import get_rating_stats
        rating_stats = get_rating_stats(user_id)
        
        return jsonify({
            'success': True,
            'message': message,
            'avg_rating': rating_stats['avg_rating'],
            'total_ratings': rating_stats['total_ratings']
        })
        
    except (ValueError, TypeError) as e:
        app.logger.error(f'ValueError/TypeError: {str(e)}')
        return jsonify({'success': False, 'message': 'Invalid rating value'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error rating user: {str(e)}', exc_info=True)
        return jsonify({'success': False, 'message': f'Failed to submit rating: {str(e)}'}), 500

@app.route('/expert-forum/user/<int:user_id>/ratings')
def user_ratings(user_id):
    """Get ratings for a user"""
    user = User.query.get_or_404(user_id)
    
    ratings = UserRating.query.filter_by(rated_user_id=user_id)\
                             .order_by(desc(UserRating.created_at))\
                             .all()
    
    # Check if current user has rated this user
    user_rating = None
    if current_user.is_authenticated:
        user_rating = UserRating.query.filter_by(
            rater_id=current_user.id,
            rated_user_id=user_id
        ).first()
    
    return jsonify({
        'ratings': [{
            'id': rating.id,
            'rating': rating.rating,
            'comment': rating.feedback,
            'rater_name': rating.rater.full_name,
            'created_at': rating.created_at.strftime('%Y-%m-%d %H:%M'),
            'is_own_rating': current_user.is_authenticated and rating.rater_id == current_user.id
        } for rating in ratings],
        'user_rating': {
            'rating': user_rating.rating,
            'comment': user_rating.feedback
        } if user_rating else None,
        'avg_rating': get_avg_rating(user_id),
        'total_ratings': len(ratings)
    })

# ============================================================================
# DRAFT ROUTES
# ============================================================================

@app.route('/expert-forum/drafts')
@login_required
def my_drafts():
    """View user's post drafts"""
    drafts = PostDraft.query.filter_by(author_id=current_user.id).order_by(desc(PostDraft.updated_at)).all()
    return render_template('expert_forum/drafts.html', drafts=drafts)

@app.route('/expert-forum/draft/save', methods=['POST'])
@login_required
def save_draft():
    """Save post as draft"""
    data = request.get_json()
    
    try:
        draft_id = data.get('draft_id')
        
        if draft_id:
            # Update existing draft
            draft = PostDraft.query.filter_by(id=draft_id, author_id=current_user.id).first_or_404()
        else:
            # Create new draft
            draft = PostDraft(author_id=current_user.id)
            db.session.add(draft)
        
        # Update draft content
        draft.title = data.get('title', '')
        draft.content = data.get('content', '')
        draft.category = data.get('category', '')
        draft.tags = data.get('tags', '')
        draft.is_question = data.get('is_question', False)
        draft.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Draft saved successfully',
            'draft_id': draft.id
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error saving draft: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to save draft'}), 400

@app.route('/expert-forum/draft/<int:draft_id>/publish', methods=['POST'])
@login_required
def publish_draft(draft_id):
    """Publish a draft as a post"""
    draft = PostDraft.query.filter_by(id=draft_id, author_id=current_user.id).first_or_404()
    
    try:
        # Create post from draft
        post = ExpertPost(
            title=draft.title,
            content=draft.content,
            category=draft.category,
            tags=draft.tags,
            is_question=draft.is_question,
            author_id=current_user.id
        )
        
        db.session.add(post)
        db.session.delete(draft)  # Remove draft
        db.session.commit()
        
        flash('Draft published successfully!', 'success')
        return redirect(url_for('view_expert_post', post_id=post.id))
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error publishing draft: {str(e)}')
        flash('Failed to publish draft', 'danger')
        return redirect(url_for('my_drafts'))

@app.route('/expert-forum/draft/<int:draft_id>/delete', methods=['POST'])
@login_required
def delete_draft(draft_id):
    """Delete a draft"""
    draft = PostDraft.query.filter_by(id=draft_id, author_id=current_user.id).first_or_404()
    
    try:
        db.session.delete(draft)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Draft deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error deleting draft: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to delete draft'}), 400

# ============================================================================
# REPORTING ROUTES
# ============================================================================

@app.route('/expert-forum/post/<int:post_id>/report', methods=['POST'])
@login_required
def report_post(post_id):
    """Report inappropriate post content"""
    post = ExpertPost.query.get_or_404(post_id)
    data = request.get_json()
    reason = data.get('reason', '').strip()
    
    if not reason:
        return jsonify({'success': False, 'message': 'Please provide a reason for reporting'}), 400
    
    try:
        # Check if user already reported this content
        existing_report = ContentReport.query.filter_by(
            content_type='post',
            content_id=post_id,
            reporter_id=current_user.id
        ).first()
        
        if existing_report:
            return jsonify({'success': False, 'message': 'You have already reported this content'}), 400
        
        # Create report
        report = ContentReport(
            content_type='post',
            content_id=post_id,
            reason=reason,
            description=data.get('description', ''),
            reporter_id=current_user.id,
            post_id=post_id
        )
        
        db.session.add(report)
        db.session.commit()
        
        # Notify admins
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            create_notification(
                user_id=admin.id,
                notification_type='content_reported',
                title='Content reported',
                message=f'Post "{post.title}" was reported for: {reason}',
                sender_id=current_user.id,
                post_id=post_id
            )
        
        return jsonify({'success': True, 'message': 'Report submitted successfully'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error reporting post: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to submit report'}), 400

@app.route('/expert-forum/reply/<int:reply_id>/report', methods=['POST'])
@login_required
def report_reply(reply_id):
    """Report inappropriate reply content"""
    reply = ExpertReply.query.get_or_404(reply_id)
    data = request.get_json()
    reason = data.get('reason', '').strip()
    
    if not reason:
        return jsonify({'success': False, 'message': 'Please provide a reason for reporting'}), 400
    
    try:
        # Check if user already reported this content
        existing_report = ContentReport.query.filter_by(
            content_type='reply',
            content_id=reply_id,
            reporter_id=current_user.id
        ).first()
        
        if existing_report:
            return jsonify({'success': False, 'message': 'You have already reported this content'}), 400
        
        # Create report
        report = ContentReport(
            content_type='reply',
            content_id=reply_id,
            reason=reason,
            description=data.get('description', ''),
            reporter_id=current_user.id,
            reply_id=reply_id
        )
        
        db.session.add(report)
        db.session.commit()
        
        # Notify admins
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            create_notification(
                user_id=admin.id,
                notification_type='content_reported',
                title='Content reported',
                message=f'Reply in "{reply.post.title}" was reported for: {reason}',
                sender_id=current_user.id,
                reply_id=reply_id
            )
        
        return jsonify({'success': True, 'message': 'Report submitted successfully'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error reporting reply: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to submit report'}), 400

# ============================================================================
# NOTIFICATION ROUTES
# ============================================================================

@app.route('/expert-forum/notifications')
@login_required
def expert_notifications():
    """View user's notifications"""
    page = request.args.get('page', 1, type=int)
    filter_type = request.args.get('filter', 'all')  # all, read, unread
    notification_type = request.args.get('type', 'all')  # all, vote, reply, follow, mention
    
    query = ForumNotification.query.filter_by(user_id=current_user.id)
    
    # Apply filters
    if filter_type == 'read':
        query = query.filter_by(is_read=True)
    elif filter_type == 'unread':
        query = query.filter_by(is_read=False)
    
    if notification_type != 'all':
        query = query.filter(ForumNotification.notification_type.contains(notification_type))
    
    notifications = query.order_by(desc(ForumNotification.created_at))\
                        .paginate(page=page, per_page=20, error_out=False)
    
    unread_count = ForumNotification.query.filter_by(
        user_id=current_user.id, 
        is_read=False
    ).count()
    
    return render_template('expert_forum/notifications.html',
                         notifications=notifications,
                         unread_count=unread_count)

@app.route('/expert-forum/notifications/<int:notification_id>/mark-read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    notification = ForumNotification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    try:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Notification marked as read'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error marking notification as read: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to mark notification as read'}), 500

@app.route('/expert-forum/notifications/mark-all-read', methods=['POST'])
@login_required
def mark_all_notifications_read():
    """Mark all notifications as read"""
    try:
        ForumNotification.query.filter_by(
            user_id=current_user.id,
            is_read=False
        ).update({
            'is_read': True,
            'read_at': datetime.utcnow()
        })
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'All notifications marked as read'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error marking all notifications as read: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to mark notifications as read'}), 500

@app.route('/expert-forum/notifications/<int:notification_id>', methods=['DELETE'])
@login_required
def delete_notification(notification_id):
    """Delete a notification"""
    notification = ForumNotification.query.filter_by(
        id=notification_id,
        user_id=current_user.id
    ).first_or_404()
    
    try:
        db.session.delete(notification)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Notification deleted'})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error deleting notification: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to delete notification'}), 500

@app.route('/expert-forum/notifications/count')
@login_required
def unread_notification_count():
    """Get count of unread notifications"""
    count = ForumNotification.query.filter_by(
        user_id=current_user.id,
        is_read=False
    ).count()
    
    return jsonify({'count': count})

@app.route('/expert-forum/notifications/preferences', methods=['GET', 'POST'])
@login_required
def notification_preferences():
    """Manage notification preferences"""
    form = NotificationPreferencesForm()
    
    if request.method == 'POST':
        if form.validate_on_submit():
            try:
                # Update preferences (implement based on your preference storage method)
                preferences = {
                    'new_replies': form.new_replies.data,
                    'post_votes': form.post_votes.data,
                    'reply_votes': form.reply_votes.data,
                    'mentions': form.mentions.data,
                    'new_followers': form.new_followers.data,
                    'user_ratings': form.user_ratings.data,
                    'followed_user_posts': form.followed_user_posts.data,
                    'post_featured': form.post_featured.data,
                    'content_reported': form.content_reported.data,
                    'system_announcements': form.system_announcements.data,
                    'email_notifications': form.email_notifications.data,
                    'email_frequency': form.email_frequency.data,
                    'quiet_hours_enabled': form.quiet_hours_enabled.data,
                    'quiet_hours_start': form.quiet_hours_start.data.strftime('%H:%M') if form.quiet_hours_start.data else None,
                    'quiet_hours_end': form.quiet_hours_end.data.strftime('%H:%M') if form.quiet_hours_end.data else None
                }
                
                # Store preferences (implement your storage method)
                session['notification_preferences'] = preferences
                
                if request.is_json:
                    return jsonify({'success': True, 'message': 'Preferences saved successfully'})
                else:
                    flash('Notification preferences saved successfully!', 'success')
                    return redirect(url_for('expert_notifications'))
                
            except Exception as e:
                app.logger.error(f'Error saving notification preferences: {str(e)}')
                if request.is_json:
                    return jsonify({'success': False, 'message': 'Failed to save preferences'}), 500
                else:
                    flash('Failed to save preferences. Please try again.', 'error')
    
    # Load current preferences
    preferences = session.get('notification_preferences', {})
    if preferences:
        for field_name, value in preferences.items():
            if hasattr(form, field_name):
                field = getattr(form, field_name)
                if field_name in ['quiet_hours_start', 'quiet_hours_end'] and value:
                    from datetime import time
                    hour, minute = map(int, value.split(':'))
                    field.data = time(hour, minute)
                else:
                    field.data = value
    
    return render_template('expert_forum/notification_preferences.html', form=form)

# ============================================================================
# SEARCH AND DISCOVERY ROUTES
# ============================================================================

@app.route('/expert-forum/search')
def advanced_search():
    """Advanced search page for expert forum"""
    from category_config import CATEGORY_STRUCTURE
    form = AdvancedSearchForm()
    
    if form.validate_on_submit():
        return redirect(url_for('expert_forum', **form.data))
    
    return render_template('expert_forum/advanced_search.html', form=form, category_structure=CATEGORY_STRUCTURE)

@app.route('/expert-forum/trending')
def trending_posts():
    """Show trending posts based on recent activity"""
    # Calculate trending score based on recent views, votes, and replies
    week_ago = datetime.utcnow() - timedelta(days=7)
    
    trending_posts = db.session.query(ExpertPost).join(ExpertReply, isouter=True).filter(
        ExpertPost.created_at > week_ago
    ).group_by(ExpertPost.id).order_by(
        desc(
            (ExpertPost.upvotes * 2) + 
            (ExpertPost.views * 0.1) + 
            (func.count(ExpertReply.id) * 3)
        )
    ).limit(20).all()
    
    return render_template('expert_forum/trending.html', posts=trending_posts)

@app.route('/expert-forum/featured')
def featured_posts():
    """Show admin-featured posts"""
    posts = ExpertPost.query.filter_by(is_featured=True).order_by(
        desc(ExpertPost.created_at)
    ).all()
    
    return render_template('expert_forum/featured.html', posts=posts)

@app.route('/expert-forum/leaderboard')
def forum_leaderboard():
    """Show user leaderboard based on reputation"""
    # Get top users by reputation in the last month
    month_ago = datetime.utcnow() - timedelta(days=30)
    
    # Get users with recent activity
    active_users = db.session.query(User.id).join(ExpertPost, isouter=True).join(
        ExpertReply, isouter=True
    ).filter(
        or_(
            ExpertPost.created_at > month_ago,
            ExpertReply.created_at > month_ago
        )
    ).distinct().all()
    
    user_ids = [u[0] for u in active_users]
    
    # Calculate reputation for these users
    leaderboard = []
    for user_id in user_ids[:50]:  # Limit to prevent performance issues
        user = User.query.get(user_id)
        if user:
            reputation = calculate_user_reputation(user_id)
            leaderboard.append({
                'user': user,
                'reputation': reputation
            })
    
    # Sort by reputation points
    leaderboard.sort(key=lambda x: x['reputation']['points'], reverse=True)
    
    return render_template('expert_forum/leaderboard.html', leaderboard=leaderboard[:20])

# ============================================================================
# ADMIN MODERATION ROUTES
# ============================================================================

@app.route('/admin/forum/reports')
@login_required
@admin_required
def admin_content_reports():
    """View all content reports for moderation"""
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', 'pending')
    
    query = ContentReport.query
    if status != 'all':
        query = query.filter_by(status=status)
    
    reports = query.order_by(desc(ContentReport.created_at)).paginate(
        page=page, per_page=20, error_out=False
    )
    
    return render_template('admin/forum_reports.html', reports=reports, current_status=status)

@app.route('/admin/forum/report/<int:report_id>/action', methods=['POST'])
@login_required
@admin_required
def moderate_content(report_id):
    """Take moderation action on reported content"""
    report = ContentReport.query.get_or_404(report_id)
    action = request.form.get('action')
    reason = request.form.get('reason', '')
    
    try:
        if action == 'approve':
            report.status = 'dismissed'
            report.moderator_notes = f'Content approved: {reason}'
            
        elif action == 'hide':
            report.status = 'resolved'
            report.moderator_notes = f'Content hidden: {reason}'
            
            # Hide the content
            if report.content_type == 'post':
                post = ExpertPost.query.get(report.content_id)
                if post:
                    post.title = "[HIDDEN]"
                    post.content = "[This content has been hidden by moderators]"
            else:
                reply = ExpertReply.query.get(report.content_id)
                if reply:
                    reply.content = "[This content has been hidden by moderators]"
                    
        elif action == 'delete':
            report.status = 'resolved'
            report.moderator_notes = f'Content deleted: {reason}'
            
            # Delete the content
            if report.content_type == 'post':
                post = ExpertPost.query.get(report.content_id)
                if post:
                    db.session.delete(post)
            else:
                reply = ExpertReply.query.get(report.content_id)
                if reply:
                    db.session.delete(reply)
                    
        elif action == 'lock_post':
            report.status = 'resolved'
            report.moderator_notes = f'Post locked: {reason}'
            
            # Lock the post
            if report.content_type == 'post':
                post = ExpertPost.query.get(report.content_id)
                if post:
                    post.is_locked = True
                    lock = PostLock(
                        post_id=post.id,
                        reason=reason,
                        moderator_id=current_user.id
                    )
                    db.session.add(lock)
        
        report.moderator_id = current_user.id
        report.resolved_at = datetime.utcnow()
        
        db.session.commit()
        flash(f'Moderation action "{action}" completed successfully.', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error taking moderation action: {str(e)}')
        flash('Failed to complete moderation action.', 'danger')
    
    return redirect(url_for('admin_content_reports'))

@app.route('/admin/forum/post/<int:post_id>/lock', methods=['POST'])
@login_required
@admin_required
def lock_post(post_id):
    """Lock/unlock a post"""
    post = ExpertPost.query.get_or_404(post_id)
    action = request.form.get('action')  # 'lock' or 'unlock'
    reason = request.form.get('reason', '')
    
    try:
        if action == 'lock':
            post.is_locked = True
            lock = PostLock(
                post_id=post_id,
                reason=reason,
                moderator_id=current_user.id
            )
            db.session.add(lock)
            message = 'Post locked successfully.'
            
        else:  # unlock
            post.is_locked = False
            # Deactivate existing locks
            PostLock.query.filter_by(post_id=post_id, is_active=True).update({'is_active': False})
            message = 'Post unlocked successfully.'
        
        db.session.commit()
        flash(message, 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error locking/unlocking post: {str(e)}')
        flash('Failed to update post lock status.', 'danger')
    
    return redirect(url_for('view_expert_post', post_id=post_id))

@app.route('/admin/forum/post/<int:post_id>/feature', methods=['POST'])
@login_required
@admin_required
def feature_post(post_id):
    """Feature/unfeature a post"""
    post = ExpertPost.query.get_or_404(post_id)
    action = request.form.get('action')  # 'feature' or 'unfeature'
    
    try:
        if action == 'feature':
            post.is_featured = True
            message = 'Post featured successfully.'
        else:  # unfeature
            post.is_featured = False
            message = 'Post unfeatured successfully.'
        
        db.session.commit()
        flash(message, 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error featuring/unfeaturing post: {str(e)}')
        flash('Failed to update post feature status.', 'danger')
    
    return redirect(url_for('view_expert_post', post_id=post_id))

@app.route('/expert-forum/admin/moderation')
@login_required
@admin_required
def admin_moderation():
    """Admin moderation panel"""
    
    # Get moderation statistics
    stats = {
        'pending_reports': ContentReport.query.filter_by(status='pending').count(),
        'locked_posts': PostLock.query.count(),
        'total_posts': ExpertPost.query.count(),
        'active_users': User.query.filter_by(is_active=True).count()
    }
    
    # Get pending reports
    pending_reports = ContentReport.query.filter_by(status='pending')\
                                        .order_by(desc(ContentReport.created_at))\
                                        .all()
    
    # Get locked content
    locked_content = PostLock.query.order_by(desc(PostLock.created_at)).all()
    
    # Get recent activity (simplified for demo)
    recent_activity = []
    
    # Get forum users with statistics
    forum_users = User.query.filter(User.id.in_(
        db.session.query(ExpertPost.author_id).distinct().union(
            db.session.query(ExpertReply.author_id).distinct()
        )
    )).all()
    
    # Add statistics to users
    for user in forum_users:
        user.post_count = ExpertPost.query.filter_by(author_id=user.id).count()
        user.reputation_score = calculate_user_reputation(user.id).get('points', 0)
        user.report_count = ContentReport.query.filter(
            or_(
                and_(ContentReport.content_type == 'post', 
                     ContentReport.post_id.in_(
                         db.session.query(ExpertPost.id).filter_by(author_id=user.id)
                     )),
                and_(ContentReport.content_type == 'reply',
                     ContentReport.reply_id.in_(
                         db.session.query(ExpertReply.id).filter_by(author_id=user.id)
                     ))
            )
        ).count()
        user.is_banned = False  # Implement based on your user model
        user.is_restricted = False  # Implement based on your user model
    
    return render_template('expert_forum/admin_moderation.html',
                         stats=stats,
                         pending_reports=pending_reports,
                         locked_content=locked_content,
                         recent_activity=recent_activity,
                         forum_users=forum_users)

@app.route('/expert-forum/admin/moderate-content', methods=['POST'])
@login_required
@admin_required
def admin_moderate_content():
    """Handle content moderation actions"""
    try:
        report_id = request.form.get('report_id')
        action = request.form.get('action')
        reason = request.form.get('reason', '')
        
        report = ContentReport.query.get_or_404(report_id)
        
        if action == 'approve':
            # Mark report as resolved - approve content
            report.status = 'resolved'
            report.resolution = 'approved'
            report.resolved_by_id = current_user.id
            report.resolved_at = datetime.utcnow()
            
            # Create notification for content author
            if report.content_type == 'post' and report.post:
                create_notification(
                    user_id=report.post.author_id,
                    notification_type='content_approved',
                    title='Content Approved',
                    message='Your reported post has been reviewed and approved.',
                    sender_id=current_user.id,
                    post_id=report.post_id
                )
            
        elif action == 'lock':
            # Lock the content
            if report.content_type == 'post' and report.post:
                lock = PostLock(
                    post_id=report.post_id,
                    locked_by_id=current_user.id,
                    reason=reason or 'Content locked pending review'
                )
                db.session.add(lock)
                
                # Update report
                report.status = 'resolved'
                report.resolution = 'locked'
                report.resolved_by_id = current_user.id
                report.resolved_at = datetime.utcnow()
                
                # Notify author
                create_notification(
                    user_id=report.post.author_id,
                    notification_type='content_locked',
                    title='Content Locked',
                    message=f'Your post has been temporarily locked: {reason}',
                    sender_id=current_user.id,
                    post_id=report.post_id
                )
            
        elif action == 'remove':
            # Remove/hide the content
            if report.content_type == 'post' and report.post:
                report.post.is_deleted = True
                report.post.deleted_at = datetime.utcnow()
                report.post.deleted_by_id = current_user.id
                
                # Notify author
                create_notification(
                    user_id=report.post.author_id,
                    notification_type='content_removed',
                    title='Content Removed',
                    message=f'Your post has been removed: {reason}',
                    sender_id=current_user.id,
                    post_id=report.post_id
                )
            elif report.content_type == 'reply' and report.reply:
                report.reply.is_deleted = True
                report.reply.deleted_at = datetime.utcnow()
                report.reply.deleted_by_id = current_user.id
                
                # Notify author
                create_notification(
                    user_id=report.reply.author_id,
                    notification_type='content_removed',
                    title='Reply Removed',
                    message=f'Your reply has been removed: {reason}',
                    sender_id=current_user.id,
                    reply_id=report.reply_id
                )
            
            # Update report
            report.status = 'resolved'
            report.resolution = 'removed'
            report.resolved_by_id = current_user.id
            report.resolved_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Content {action}ed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error moderating content: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to moderate content'}), 500

@app.route('/expert-forum/admin/unlock-content', methods=['POST'])
@login_required
@admin_required
def unlock_content():
    """Unlock locked content"""
    try:
        content_id = request.form.get('content_id')
        content_type = request.form.get('content_type')
        
        if content_type == 'post':
            lock = PostLock.query.filter_by(post_id=content_id).first_or_404()
            post = ExpertPost.query.get_or_404(content_id)
            
            # Remove lock
            db.session.delete(lock)
            
            # Notify author
            create_notification(
                user_id=post.author_id,
                notification_type='content_unlocked',
                title='Content Unlocked',
                message='Your post has been unlocked and is now visible.',
                sender_id=current_user.id,
                post_id=content_id
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Content unlocked successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error unlocking content: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to unlock content'}), 500

@app.route('/expert-forum/admin/remove-content', methods=['POST'])
@login_required
@admin_required
def remove_locked_content():
    """Remove locked content permanently"""
    try:
        content_id = request.form.get('content_id')
        content_type = request.form.get('content_type')
        
        if content_type == 'post':
            post = ExpertPost.query.get_or_404(content_id)
            lock = PostLock.query.filter_by(post_id=content_id).first()
            
            # Mark as deleted
            post.is_deleted = True
            post.deleted_at = datetime.utcnow()
            post.deleted_by_id = current_user.id
            
            # Remove lock
            if lock:
                db.session.delete(lock)
            
            # Notify author
            create_notification(
                user_id=post.author_id,
                notification_type='content_removed',
                title='Content Removed',
                message='Your locked post has been permanently removed.',
                sender_id=current_user.id,
                post_id=content_id
            )
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Content removed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error removing content: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to remove content'}), 500

@app.route('/expert-forum/admin/moderate-user', methods=['POST'])
@login_required
@admin_required
def moderate_user():
    """Handle user moderation actions"""
    try:
        user_id = request.form.get('user_id')
        action = request.form.get('action')
        reason = request.form.get('reason', '')
        
        user = User.query.get_or_404(user_id)
        
        # Implement user moderation based on your user model
        if action == 'restrict':
            # Implement user restriction logic
            pass
        elif action == 'unrestrict':
            # Implement user unrestriction logic
            pass
        elif action == 'ban':
            # Implement user banning logic
            user.is_active = False
        elif action == 'unban':
            # Implement user unbanning logic
            user.is_active = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'User {action}ed successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f'Error moderating user: {str(e)}')
        return jsonify({'success': False, 'message': 'Failed to moderate user'}), 500

# ============================================================================
# ANALYTICS ROUTES
# ============================================================================

@app.route('/admin/forum/analytics')
@login_required
@admin_required
def forum_analytics():
    """Admin analytics for forum activity"""
    # Get various statistics
    stats = {
        'total_posts': ExpertPost.query.count(),
        'total_replies': ExpertReply.query.count(),
        'total_users': User.query.count(),
        'active_users_week': db.session.query(func.count(func.distinct(ExpertPost.author_id))).filter(
            ExpertPost.created_at > datetime.utcnow() - timedelta(days=7)
        ).scalar(),
        'answered_questions': ExpertPost.query.filter_by(is_answered=True).count(),
        'pending_reports': ContentReport.query.filter_by(status='pending').count()
    }
    
    # Get category distribution
    category_stats = db.session.query(
        ExpertPost.category,
        func.count(ExpertPost.id).label('count')
    ).group_by(ExpertPost.category).order_by(desc('count')).all()
    
    # Get daily post counts for the last 30 days
    daily_posts = []
    for i in range(30):
        date = datetime.utcnow().date() - timedelta(days=i)
        count = ExpertPost.query.filter(
            func.date(ExpertPost.created_at) == date
        ).count()
        daily_posts.append({'date': date.strftime('%Y-%m-%d'), 'count': count})
    
    daily_posts.reverse()
    
    return render_template('admin/forum_analytics.html',
                         stats=stats,
                         category_stats=category_stats,
                         daily_posts=daily_posts)
