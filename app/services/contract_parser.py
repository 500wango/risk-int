import re
import io
import pdfplumber
import docx
from fastapi import UploadFile

class ContractParser:
    
    @staticmethod
    def clean_text(text: str) -> str:
        # Basic cleanup
        return re.sub(r'\s+', ' ', text).strip()

    @staticmethod
    async def parse_file(file: UploadFile) -> str:
        filename = file.filename.lower()
        content = ""
        
        # 读取文件内容到内存
        file_content = await file.read()
        file_stream = io.BytesIO(file_content)
        
        if filename.endswith(".pdf"):
            with pdfplumber.open(file_stream) as pdf:
                for page in pdf.pages:
                    content += page.extract_text() + "\n"
                    
        elif filename.endswith(".docx"):
            doc = docx.Document(file_stream)
            for para in doc.paragraphs:
                content += para.text + "\n"
        
        return ContractParser.clean_text(content)

    @staticmethod
    def desensitize(text: str) -> str:
        # MVP Logic: Mask Money and Dates (Simple Regex)
        # Mask Money: $1,000,000 or ¥100m
        text = re.sub(r'(\$|€|¥|£|RMB|USD)\s?\d+(,\d{3})*(\.\d+)?', '[AMOUNT]', text)
        # Mask Dates: 2024-01-01 or January 1, 2024
        text = re.sub(r'\d{4}-\d{2}-\d{2}', '[DATE]', text)
        return text

    @staticmethod
    def local_rule_check(text: str) -> list:
        """
        Comprehensive contract risk detection using regex patterns.
        Supports both English and Chinese keywords.
        Risk categories aligned with AI engine prompt.
        """
        risks = []
        
        # Define all rules with regex patterns (categories aligned with AI prompt)
        rules = [
            # 单方权利条款
            {
                "id": "R1",
                "pattern": r"(terminate|unilateral|单方.{0,5}解约|无过错.{0,5}解约|任意.{0,5}终止|单方.{0,5}终止)",
                "risk_category": "单方解约权",
                "risk_level": "High",
                "explanation": "合同包含单方解约或无过错解约条款，可能导致对方随时终止合同而无需承担责任。"
            },
            {
                "id": "R2",
                "pattern": r"(price.{0,10}adjust|单方.{0,5}调价|可.{0,10}调整价格|价格.{0,5}变更|单方.{0,5}定价)",
                "risk_category": "单方调价权",
                "risk_level": "High",
                "explanation": "合同允许单方调整价格，可能导致成本不可控。"
            },
            {
                "id": "R6",
                "pattern": r"(may amend|unilateral.{0,5}(change|modify)|单方.{0,5}(修改|变更|调整)|可.{0,10}(修改|变更).{0,5}条款)",
                "risk_category": "单方变更权",
                "risk_level": "High",
                "explanation": "合同允许单方修改条款，可能导致权益受损。"
            },
            # 定价与金融风险
            {
                "id": "R3",
                "pattern": r"(currency|fx|汇率|定价货币|支付货币|币种|exchange rate|外汇)",
                "risk_category": "定价与汇率风险",
                "risk_level": "Medium",
                "explanation": "合同涉及多种货币或汇率条款，可能存在汇率波动风险。"
            },
            # 责任与免责
            {
                "id": "R4",
                "pattern": r"(liabilit|indemnif|免责|不承担.{0,5}责任|责任.{0,5}免除|概不负责)",
                "risk_category": "免责条款",
                "risk_level": "High",
                "explanation": "合同包含免责条款，可能导致对方不承担应有责任。"
            },
            {
                "id": "R7",
                "pattern": r"(liquidated damages|penalt|late fee|违约金|滞纳金|罚金|逾期.{0,5}赔偿)",
                "risk_category": "违约金条款",
                "risk_level": "High",
                "explanation": "合同包含违约金或罚金条款，需评估金额合理性。"
            },
            {
                "id": "R8",
                "pattern": r"(unlimited liabilit|no limit|not limited|不设上限|无上限|不受限制|无限.{0,5}责任)",
                "risk_category": "无限责任风险",
                "risk_level": "High",
                "explanation": "合同责任不设上限，可能面临无限赔偿风险。"
            },
            # 担保与履约保障
            {
                "id": "R5",
                "pattern": r"(guarantee|security|担保|保证责任|无担保|履约保函|保证金)",
                "risk_category": "担保缺失",
                "risk_level": "Medium",
                "explanation": "合同担保条款缺失或弱化，增加履约风险。"
            },
            # 政府承诺与公共部门义务
            {
                "id": "R12",
                "pattern": r"(government.{0,10}commit|政府.{0,5}承诺|政策.{0,5}保障|公共部门|sovereign|政府.{0,5}保证)",
                "risk_category": "政府承诺风险",
                "risk_level": "Medium",
                "explanation": "涉及政府承诺条款，需评估承诺的法律约束力。"
            },
            # 不可抗力与政策变更
            {
                "id": "R13",
                "pattern": r"(force majeure|不可抗力|政策变更|法律变更|change.{0,5}law|法规.{0,5}变化)",
                "risk_category": "不可抗力滥用",
                "risk_level": "Medium",
                "explanation": "不可抗力或政策变更条款可能被滥用，需审查定义范围。"
            },
            # 劳工、本地化与环保
            {
                "id": "R14",
                "pattern": r"(local.{0,5}content|本地化|localization|当地.{0,5}比例|环保|environmental|本地.{0,5}采购)",
                "risk_category": "本地化与环保责任",
                "risk_level": "Medium",
                "explanation": "本地化或环保要求可能增加履约成本和合规风险。"
            },
            # 争议解决
            {
                "id": "R9",
                "pattern": r"(arbitration|governing law|jurisdiction|venue|仲裁|管辖|适用法律|法院|争议解决)",
                "risk_category": "争议解决条款",
                "risk_level": "Medium",
                "explanation": "需审查管辖地、适用法律及争议解决方式是否对己方有利。"
            },
            # 其他
            {
                "id": "R10",
                "pattern": r"(exclusive|exclusivity|non-compete|排他|独家|竞业|独占)",
                "risk_category": "排他/竞业限制",
                "risk_level": "Medium",
                "explanation": "合同包含排他或竞业限制条款，可能限制业务发展。"
            },
            {
                "id": "R11",
                "pattern": r"(assign(ment)?|transfer|合同.{0,3}转让|权利.{0,3}转让|义务.{0,3}转让)",
                "risk_category": "合同转让",
                "risk_level": "Low",
                "explanation": "合同包含转让条款，需确认转让条件和限制。"
            },
        ]
        
        for rule in rules:
            matches = list(re.finditer(rule["pattern"], text, re.IGNORECASE))
            if matches:
                # Take the first match
                match = matches[0]
                start = max(0, match.start() - 40)
                end = min(len(text), match.end() + 40)
                context = text[start:end].strip()
                # Clean up context
                context = re.sub(r'\s+', ' ', context)
                if len(context) > 120:
                    context = context[:120] + "..."
                    
                risks.append({
                    "clause_id": rule["id"],
                    "clause_text": f"「{context}」",
                    "risk_category": rule["risk_category"],
                    "risk_level": rule["risk_level"],
                    "risk_reason": f"规则检测: {rule['risk_category']}",
                    "explanation": rule["explanation"],
                    "confidence": 0.85
                })
        
        return risks

contract_parser = ContractParser()
