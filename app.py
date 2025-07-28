import pandas as pd
import numpy as np
from flask import Flask, jsonify
from flask_cors import CORS
import psycopg2
from dotenv import load_dotenv
import os
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import TruncatedSVD
from sklearn.metrics import silhouette_score
import logging
from scrap import scrap, verify_letterboxd_user

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["https://letterbesdfront.vercel.app"])

load_dotenv()

dbname = os.getenv("DB_NAME")
user = os.getenv("DB_USER")
password = os.getenv("DB_PASSWORD")
host = os.getenv("DB_HOST")
port = os.getenv("DB_PORT")

def get_db_connection():
    return psycopg2.connect(
        dbname=dbname,
        user=user,
        password=password,
        host=host,
        port=port
    )

def adicionar_usuario(usuario):
    logger.info(f"Tentando adicionar usuário {usuario} ao banco de dados")
    if not verify_letterboxd_user(usuario):
        logger.error(f"Usuário {usuario} não existe no Letterboxd")
        return False
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            scrap(cursor, conn, usuario)
        conn.close()
        logger.info(f"Usuário {usuario} adicionado com sucesso")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário {usuario}: {str(e)}")
        return False

def gerar_recomendacoes(usuario_alvo):
    logger.info(f"Iniciando geração de recomendações para usuário: {usuario_alvo}")
    try:
        conn = get_db_connection()
        query = """
        SELECT u.username, m.title, r.rating
        FROM ratings r
        JOIN users u ON r.user_id = u.id
        JOIN movies m ON r.movie_id = m.id
        """
        logger.info("Executando query para buscar avaliações")
        df = pd.read_sql(query, conn)
        conn.close()
        logger.info(f"Total de registros encontrados: {len(df)}")

        if len(df) < 2:
            logger.warning("Dados insuficientes para gerar recomendações")
            return {
                "error": "Não há dados suficientes para gerar recomendações",
                "status": "insufficient_data",
                "message": "É necessário ter pelo menos 2 usuários com avaliações para gerar recomendações",
                "recomendacoes": {},
                "metadata": {
                    "total_usuarios": 0,
                    "total_filmes": 0,
                    "filmes_nao_vistos": 0,
                    "total_recomendacoes": 0
                }
            }

        logger.info("Criando matriz de usuário-filme")
        rating_matrix = df.pivot_table(
            index='username',
            columns='title',
            values='rating'
        ).fillna(0)

        if usuario_alvo not in rating_matrix.index:
            logger.info(f"Usuário {usuario_alvo} não encontrado no banco de dados. Tentando adicionar...")
            if adicionar_usuario(usuario_alvo):
                logger.info("Usuário adicionado com sucesso. Gerando recomendações...")
                return gerar_recomendacoes(usuario_alvo)
            else:
                logger.warning(f"Falha ao adicionar usuário {usuario_alvo}")
                return {
                    "error": f"Usuário {usuario_alvo} não encontrado no Letterboxd ou erro ao adicionar",
                    "status": "user_not_found",
                    "message": "O usuário não foi encontrado no banco de dados ou não existe no Letterboxd. Verifique o nome.",
                    "recomendacoes": {}, 
                    "metadata": {
                        "total_usuarios": len(rating_matrix) if not rating_matrix.empty else 0,
                        "total_filmes": 0,
                        "filmes_nao_vistos": 0,
                        "total_recomendacoes": 0
                    }
                }

        filmes_usuario = df[df['username'] == usuario_alvo]['title'].unique()
        todos_filmes = df['title'].unique()
        filmes_nao_vistos = set(todos_filmes) - set(filmes_usuario)

        if len(rating_matrix) < 4:
            logger.info("Usando abordagem simples para poucos usuários")
            recomendacoes = []
            for filme in filmes_nao_vistos:
                if filme in rating_matrix.columns:
                    avaliacoes = df[df['title'] == filme]['rating']
                    media = avaliacoes.mean()
                    num_avaliacoes = len(avaliacoes)
                    if not np.isnan(media):
                        score = media * (1 + 0.1 * num_avaliacoes)
                        recomendacoes.append({
                            'filme': filme,
                            'score': float(score)
                        })
        else:
            logger.info("Normalizando e reduzindo dimensionalidade")
            scaler = StandardScaler()
            rating_matrix_scaled = scaler.fit_transform(rating_matrix)

           
            n_components = min(30, min(rating_matrix_scaled.shape)-1)
            if n_components < 1:
                rating_matrix_reduced = rating_matrix_scaled
            else:
                svd = TruncatedSVD(n_components=n_components, random_state=42)
                rating_matrix_reduced = svd.fit_transform(rating_matrix_scaled)

            sil_scores = []
            possible_ks = range(2, min(11, len(rating_matrix))) 
            if not possible_ks:
                 best_k = 1
            else:
                for k in possible_ks:
                    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                    labels = kmeans.fit_predict(rating_matrix_reduced)
                    if len(set(labels)) > 1:
                        score = silhouette_score(rating_matrix_reduced, labels)
                        sil_scores.append(score)
                    else:
                        sil_scores.append(-1) 
                best_k = possible_ks[np.argmax(sil_scores)] if sil_scores and max(sil_scores) > -1 else 2

            logger.info(f"Melhor número de clusters: {best_k}")
            kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=20)
            clusters = kmeans.fit_predict(rating_matrix_reduced)
            rating_matrix['cluster'] = clusters

            cluster_usuario = rating_matrix.loc[usuario_alvo, 'cluster']
            logger.info(f"Usuário {usuario_alvo} está no cluster {cluster_usuario}")

            usuarios_mesmo_cluster = rating_matrix[rating_matrix['cluster'] == cluster_usuario].index
            logger.info(f"Total de usuários no mesmo cluster: {len(usuarios_mesmo_cluster)}")

            if len(usuarios_mesmo_cluster) < 2:
                logger.info("Poucos usuários no mesmo cluster, usando todos os usuários")
                usuarios_mesmo_cluster = rating_matrix.index

            logger.info("Calculando scores de recomendação")
            recomendacoes = []
            for filme in filmes_nao_vistos:
                if filme in rating_matrix.columns:
                    avaliacoes = df[
                        (df['title'] == filme) &
                        (df['username'].isin(usuarios_mesmo_cluster))
                    ]['rating']
                    if len(avaliacoes) > 0:
                        media = avaliacoes.mean()
                        num_avaliacoes = len(avaliacoes)
                        if not np.isnan(media):
                            score = media * (1 + 0.1 * num_avaliacoes)
                            recomendacoes.append({
                                'filme': filme,
                                'score': float(score)
                            })

            if len(recomendacoes) < 10:
                logger.info("Adicionando filmes populares para completar recomendações")
                filmes_populares = []
                for filme in filmes_nao_vistos:
                    if filme not in [r['filme'] for r in recomendacoes]:
                        avaliacoes = df[df['title'] == filme]['rating']
                        media = avaliacoes.mean()
                        num_avaliacoes = len(avaliacoes)
                        if not np.isnan(media):
                            score = media * (1 + 0.1 * num_avaliacoes)
                            filmes_populares.append({
                                'filme': filme,
                                'score': float(score)
                            })
                filmes_populares.sort(key=lambda x: x['score'], reverse=True)
                novos_populares = [f for f in filmes_populares if f['filme'] not in [r['filme'] for r in recomendacoes]]
                recomendacoes.extend(novos_populares[:10 - len(recomendacoes)])


        recomendacoes.sort(key=lambda x: x['score'], reverse=True)
        recomendacoes_formatadas = {rec['filme']: rec['score'] for rec in recomendacoes[:10]}
        response = {
            "status": "success",
            "message": "Recomendações geradas com sucesso",
            "recomendacoes": recomendacoes_formatadas,
            "metadata": {
                "total_usuarios": len(rating_matrix),
                "total_filmes": len(todos_filmes),
                "filmes_nao_vistos": len(filmes_nao_vistos),
                "total_recomendacoes": len(recomendacoes_formatadas) 
            }
        }
        logger.info("Recomendações geradas com sucesso")
        return response

    except Exception as e:
        logger.error(f"Erro ao gerar recomendações: {str(e)}")
        return {
            "error": str(e),
            "status": "error",
            "message": "Ocorreu um erro ao gerar as recomendações",
            "recomendacoes": {},
            "metadata": {
                "total_usuarios": 0,
                "total_filmes": 0,
                "filmes_nao_vistos": 0,
                "total_recomendacoes": 0
            }
        }

@app.route('/api/recomendacoes/<usuario>')
def obter_recomendacoes(usuario):
    logger.info(f"Recebida requisição para usuário: {usuario}")
    try:
        recomendacoes = gerar_recomendacoes(usuario)
        logger.info(f"Resposta gerada: {recomendacoes}")
        return jsonify(recomendacoes)
    except Exception as e:
        logger.error(f"Erro na rota de recomendações: {str(e)}")
        return jsonify({
            "error": str(e),
            "status": "error",
            "message": "Ocorreu um erro ao processar a requisição",
            "recomendacoes": {},
            "metadata": {
                "total_usuarios": 0,
                "total_filmes": 0,
                "filmes_nao_vistos": 0,
                "total_recomendacoes": 0
            }
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
